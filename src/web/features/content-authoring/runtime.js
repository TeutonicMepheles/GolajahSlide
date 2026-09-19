    class ContentAuthoring {
      static schemaVersion = "1.0";
      static movableKinds = new Set(["text", "callout", "image", "video"]);
      static blockKinds = new Set(["text", "callout"]);
      static mediaKinds = new Set(["image", "video"]);

      static readEmbeddedModel(id = "deckAuthoringModel") {
        try {
          const payload = JSON.parse(document.getElementById(id)?.textContent || "{}");
          return payload && typeof payload === "object" ? payload : {};
        } catch (_) {
          return {};
        }
      }

      constructor(options = {}) {
        this.stage = typeof options.stage === "string"
          ? document.querySelector(options.stage)
          : (options.stage || document.getElementById("deckStage"));
        if (!this.stage) throw new Error("Content Authoring requires a deck stage");
        this.presentation = options.presentation || null;
        this.layoutEditor = options.layoutEditor || null;
        this.widgetManager = options.widgetManager || null;
        this.mediaTabsManager = options.mediaTabsManager || null;
        this.mediaPlayback = options.mediaPlayback || null;
        this.domBridge = options.domBridge || null;
        this.saveAdapter = options.saveAdapter || null;
        this.serializeBridge = typeof options.serializeMarkdown === "function" ? options.serializeMarkdown : null;
        this.mediaImporter = options.mediaImporter || null;
        this.manifest = this.normalizeManifest(options.manifest || ContentAuthoring.readEmbeddedModel());
        this.source = {...this.manifest.source};
        this.slideStates = new Map();
        this.items = new Map();
        this.nodes = new Map();
        this.pendingAssets = new Map();
        this.operations = [];
        this.revision = 0;
        this.selectedId = null;
        this.active = false;
        this.dirty = false;
        this.needsRebuild = false;
        this.storageWarning = "";
        this.staleDraft = null;
        this.fieldTimers = new Map();
        this.abortController = new AbortController();
        this.panelWasCreated = false;
        this.initializeModel();
        this.mountPanel(options.panelRoot || null);
        this.bind();
        this.restoreDraft();
        this.refreshPanel();
      }

      normalizeManifest(value) {
        const manifest = value && typeof value === "object" ? value : {};
        const source = manifest.source && typeof manifest.source === "object" ? manifest.source : {};
        const slides = Array.isArray(manifest.slides)
          ? manifest.slides
          : Object.entries(manifest.slides || {}).map(([id, slide]) => ({id, ...(slide || {})}));
        return {
          schemaVersion: String(manifest.schemaVersion || ContentAuthoring.schemaVersion),
          source: {
            name: String(source.name || source.path || "slides.md"),
            sha256: String(source.sha256 || source.sourceSha256 || ""),
            text: typeof source.text === "string" ? source.text : "",
            newline: ["\n", "\r\n", "\r"].includes(source.newline) ? source.newline : "\n",
            bom: source.bom === true,
            offsetEncoding: String(source.offsetEncoding || "utf-16"),
            layoutName: String(source.layoutName || ""),
            layoutSha256: String(source.layoutSha256 || "")
          },
          slides: slides.filter(slide => slide && typeof slide === "object" && slide.id)
        };
      }

      initializeModel() {
        const manifestSlides = new Map(this.manifest.slides.map(slide => [String(slide.id), slide]));
        const slideNodes = [...this.stage.querySelectorAll(":scope > .slide[data-slide-id]")];
        slideNodes.forEach((element, index) => {
          const id = String(element.dataset.slideId || "");
          const authored = manifestSlides.get(id) || {};
          const state = {
            id,
            index,
            element,
            kind: String(element.dataset.slideKind || authored.kind || "content"),
            number: Number(authored.number || index + 1),
            title: String(authored.title ?? element.dataset.title ?? ""),
            subtitle: String(authored.subtitle || ""),
            baseHash: String(authored.baseHash || element.dataset.authorBaseHash || ""),
            source: typeof authored.source === "string" ? authored.source : "",
            sourceRange: this.normalizeRange(authored.sourceRange),
            directiveRange: this.normalizeRange(authored.directiveRange),
            titleRange: this.normalizeRange(authored.titleRange),
            subtitleRange: this.normalizeRange(authored.subtitleRange),
            config: authored.config && typeof authored.config === "object" ? {...authored.config} : {},
            section: String(authored.effectiveSection ?? element.dataset.section ?? authored.config?.section ?? ""),
            chapter: String(authored.config?.chapter || element.dataset.chapter || ""),
            baseChapter: String(authored.config?.chapter || element.dataset.chapter || ""),
            chapterChanged: false,
            layoutResolved: String(element.dataset.layoutResolved || authored.layoutResolved || authored.config?.layout || "text"),
            layoutChanged: false,
            galleryDisplay: authored.galleryDisplay === "tabs" ? "tabs" : "grid",
            baseGalleryDisplay: authored.galleryDisplay === "tabs" ? "tabs" : "grid",
            itemIds: [],
            baseItemIds: [],
            galleryChanged: false,
            contentChanged: false,
            changed: false
          };
          this.slideStates.set(id, state);
          const authoredItems = Array.isArray(authored.items) ? authored.items : [];
          authoredItems.forEach(item => this.registerItem(state, item));
          element.querySelectorAll("[data-author-item-id][data-author-item-kind]").forEach(node => {
            const itemId = String(node.dataset.authorItemId || "");
            if (!itemId || this.items.has(itemId)) {
              if (itemId) this.nodes.set(itemId, node);
              return;
            }
            this.registerItem(state, {
              id: itemId,
              kind: node.dataset.authorItemKind,
              baseHash: node.dataset.authorBaseHash || "",
              title: this.readField(node, "title"),
              body: this.readField(node, "body"),
              caption: this.readField(node, "caption")
            });
          });
          state.baseItemIds = [...state.itemIds];
        });
      }

      registerItem(state, source) {
        const id = String(source?.id || "");
        const kind = String(source?.kind || "").toLowerCase();
        if (!id || this.items.has(id)) return null;
        const node = [...state.element.querySelectorAll("[data-author-item-id]")]
          .find(candidate => candidate.dataset.authorItemId === id) || null;
        const item = {
          id,
          kind,
          slideId: state.id,
          title: String(source.title ?? this.readField(node, "title") ?? ""),
          body: String(source.body ?? this.readField(node, "body") ?? ""),
          caption: String(source.caption ?? this.readField(node, "caption") ?? ""),
          alt: String(source.alt || node?.querySelector("img,video")?.getAttribute("alt") || ""),
          calloutKind: String(source.calloutKind || source["callout-kind"] || source.variant || "note").toLowerCase(),
          markdown: typeof source.markdown === "string" ? source.markdown : "",
          baseHash: String(source.baseHash || node?.dataset.authorBaseHash || ""),
          sourceRange: this.normalizeRange(source.sourceRange),
          fieldRanges: this.normalizeFieldRanges(source.fieldRanges),
          assetId: String(source.assetId || ""),
          sourcePath: String(source.sourcePath || source.source || source.src || ""),
          width: Number(source.width) || null,
          height: Number(source.height) || null,
          created: source.created === true,
          dirtyFields: new Set(Array.isArray(source.dirtyFields) ? source.dirtyFields.map(String) : [])
        };
        this.items.set(id, item);
        state.itemIds.push(id);
        if (node) this.nodes.set(id, node);
        return item;
      }

      normalizeRange(value) {
        if (!value || typeof value !== "object") return null;
        const start = Number(value.start);
        const end = Number(value.end);
        return Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end >= start ? {start, end} : null;
      }

      normalizeFieldRanges(value) {
        if (!value || typeof value !== "object") return {};
        return Object.fromEntries(Object.entries(value)
          .map(([name, range]) => [name, this.normalizeRange(range)])
          .filter(([, range]) => range));
      }

      readField(node, name) {
        if (!node) return "";
        const field = node.matches?.(`[data-author-field="${name}"]`)
          ? node
          : node.querySelector?.(`[data-author-field="${name}"]`);
        return field?.innerText?.replace(/\u00a0/g, " ").trim() || "";
      }

      mountPanel(panelRoot) {
        let root = typeof panelRoot === "string" ? document.querySelector(panelRoot) : panelRoot;
        if (!root) root = document.querySelector("[data-content-authoring-mount]");
        if (!root) {
          const editorBody = document.querySelector("#layoutEditorPanel .layout-editor-body");
          if (!editorBody) return;
          root = document.createElement("section");
          root.className = "editor-group content-authoring-panel";
          root.dataset.contentAuthoringMount = "";
          editorBody.insertBefore(root, editorBody.querySelector(".editor-status"));
          this.panelWasCreated = true;
        }
        root.classList.add("content-authoring-panel");
        root.innerHTML = `
          <div class="editor-toggle-row content-authoring-heading">
            <div><div class="editor-label">结构化内容 <span>当前页</span></div><p class="editor-help">选择内容后可编辑、排序或移动到相邻页。</p></div>
            <button type="button" class="editor-button" data-author-action="toggle-mode" aria-pressed="false">内容模式</button>
          </div>
          <section class="content-authoring-chapter" data-author-chapter-panel>
            <label class="editor-label" for="editorChapterItem">Chapter item <span data-author-section-name>当前 Section</span></label>
            <select class="editor-select" id="editorChapterItem" data-author-chapter-select></select>
            <div class="editor-button-row content-authoring-chapter-actions">
              <button type="button" class="editor-button" data-author-action="show-new-chapter">＋ 新增 item</button>
            </div>
            <div class="content-authoring-chapter-create" data-author-chapter-create hidden>
              <input type="text" maxlength="80" autocomplete="off" placeholder="输入新的 Chapter item 名称" data-author-chapter-input aria-label="新的 Chapter item 名称">
              <button type="button" class="editor-button primary" data-author-action="add-chapter">新增并归属</button>
            </div>
            <p class="editor-help" data-author-chapter-help>保存并重新构建后，页脚 Chapter 导航会同步更新。</p>
          </section>
          <div class="editor-button-row content-authoring-add-row">
            <button type="button" class="editor-button primary" data-author-action="add-text">＋ 文本块</button>
            <button type="button" class="editor-button" data-author-action="add-callout">＋ Callout</button>
          </div>
          <button type="button" class="editor-button content-authoring-upload" data-author-action="upload-image">上传 / 替换图片</button>
          <input type="file" data-author-image-input accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" multiple hidden>
          <fieldset class="content-authoring-gallery" data-author-gallery hidden>
            <legend>多图展示</legend>
            <div class="content-authoring-segmented">
              <button type="button" data-author-gallery-display="grid" aria-pressed="false">并列</button>
              <button type="button" data-author-gallery-display="tabs" aria-pressed="false">Gallery</button>
            </div>
          </fieldset>
          <ol class="content-authoring-order" data-author-order aria-label="文本块与 Callout 顺序"></ol>
          <div class="content-authoring-selection" data-author-selection hidden>
            <div class="editor-label">已选内容 <span data-author-selection-kind></span></div>
            <label class="content-authoring-field" data-author-title-row><span>标题</span><input type="text" data-author-input="title"></label>
            <label class="content-authoring-field" data-author-body-row><span>正文</span><textarea rows="4" data-author-input="body"></textarea></label>
            <div class="editor-button-row">
              <button type="button" class="editor-button" data-author-action="move-prev">移到上一页</button>
              <button type="button" class="editor-button" data-author-action="move-next">移到下一页</button>
            </div>
          </div>
          <button type="button" class="editor-button primary content-authoring-save" data-author-action="save" disabled>保存改动</button>
          <p class="content-authoring-status" data-author-status role="status">尚无内容改动。</p>`;
        this.panel = root;
        this.orderList = root.querySelector("[data-author-order]");
        this.selectionPanel = root.querySelector("[data-author-selection]");
        this.statusNode = root.querySelector("[data-author-status]");
        this.saveButton = root.querySelector('[data-author-action="save"]');
        this.modeButton = root.querySelector('[data-author-action="toggle-mode"]');
        this.imageInput = root.querySelector("[data-author-image-input]");
        this.chapterSelect = root.querySelector("[data-author-chapter-select]");
        this.chapterCreate = root.querySelector("[data-author-chapter-create]");
        this.chapterInput = root.querySelector("[data-author-chapter-input]");
      }

      bind() {
        const signal = this.abortController.signal;
        this.stage.addEventListener("click", event => this.handleStageClick(event), {signal});
        this.stage.addEventListener("focusin", event => this.handleFieldFocus(event), {signal});
        this.stage.addEventListener("input", event => this.handleFieldInput(event), {signal});
        this.stage.addEventListener("focusout", event => this.handleFieldBlur(event), {signal});
        this.stage.addEventListener("paste", event => this.handlePaste(event), {signal});
        this.stage.addEventListener("dragover", event => this.handleStageDragOver(event), {signal});
        this.stage.addEventListener("drop", event => this.handleStageDrop(event), {signal});
        addEventListener("keydown", event => {
          if (!this.active || event.defaultPrevented || event.isComposing || event.keyCode === 229) return;
          if (event.key === "Escape" && this.selectedId) {
            event.preventDefault();
            this.select(null);
          }
        }, {capture: true, signal});
        if (this.panel) {
          this.panel.addEventListener("click", event => this.handlePanelClick(event), {signal});
          this.panel.addEventListener("change", event => this.handlePanelChange(event), {signal});
          this.panel.addEventListener("keydown", event => {
            if (event.key !== "Enter" || event.isComposing || event.keyCode === 229 || !event.target.matches("[data-author-chapter-input]")) return;
            event.preventDefault();
            this.addChapterFromInput();
          }, {signal});
          this.orderList.addEventListener("dragstart", event => this.handleOrderDragStart(event), {signal});
          this.orderList.addEventListener("dragover", event => this.handleOrderDragOver(event), {signal});
          this.orderList.addEventListener("drop", event => this.handleOrderDrop(event), {signal});
          this.orderList.addEventListener("dragend", () => this.clearOrderDrag(), {signal});
        }
        this.bodyObserver = new MutationObserver(() => {
          if (!document.body.classList.contains("editor-open") && this.active) this.setActive(false);
        });
        this.bodyObserver.observe(document.body, {attributes: true, attributeFilter: ["class"]});
      }

      destroy() {
        this.setActive(false);
        this.abortController.abort();
        this.bodyObserver?.disconnect();
        this.fieldTimers.forEach(timer => clearTimeout(timer));
        if (this.panelWasCreated) this.panel?.remove();
      }

      setActive(active) {
        this.active = active === true;
        document.body.classList.toggle("content-authoring-active", this.active);
        this.modeButton?.setAttribute("aria-pressed", String(this.active));
        if (this.modeButton) this.modeButton.textContent = this.active ? "结束内容模式" : "内容模式";
        if (this.active) {
          this.layoutEditor?.setAnimationMode?.(false);
          this.layoutEditor?.setTextMode?.(false);
          this.layoutEditor?.setInteractionMode?.("content");
        } else {
          this.layoutEditor?.setInteractionMode?.("layout");
          this.select(null);
        }
        this.setFieldsEditable(this.active);
        this.widgetManager?.setEditing?.(document.body.classList.contains("editor-open") || this.active);
        this.dispatch("mode-change", {active: this.active});
        this.refreshPanel();
      }

      setFieldsEditable(editable) {
        this.stage.querySelectorAll("[data-author-item-id] [data-author-field]").forEach(field => {
          if (editable && ContentAuthoring.movableKinds.has(field.closest("[data-author-item-kind]")?.dataset.authorItemKind)) {
            field.setAttribute("contenteditable", "plaintext-only");
            field.setAttribute("spellcheck", "true");
            const itemId = field.closest("[data-author-item-id]")?.dataset.authorItemId;
            field.dataset.authorEditKey = `${itemId}:${field.dataset.authorField}`;
          } else {
            field.removeAttribute("contenteditable");
            field.removeAttribute("spellcheck");
          }
        });
      }

      handleStageClick(event) {
        if (!this.active || event.target.closest("button,a,input,textarea,select")) return;
        const node = event.target.closest("[data-author-item-id][data-author-item-kind]");
        if (!node || !node.closest(".slide.active")) {
          this.select(null);
          return;
        }
        const item = this.items.get(node.dataset.authorItemId);
        if (!item || !ContentAuthoring.movableKinds.has(item.kind)) return;
        event.stopPropagation();
        this.select(item.id);
      }

      handleFieldFocus(event) {
        if (!this.active) return;
        const field = event.target.closest?.("[data-author-field]");
        const itemId = field?.closest("[data-author-item-id]")?.dataset.authorItemId;
        if (itemId && this.items.has(itemId)) this.select(itemId, {focusPanel: false});
      }

      handleFieldInput(event) {
        const field = event.target.closest?.("[data-author-field]");
        if (!this.active || !field) return;
        event.stopPropagation();
        const itemId = field.closest("[data-author-item-id]")?.dataset.authorItemId;
        const name = field.dataset.authorField;
        if (!itemId || !name) return;
        const key = `${itemId}:${name}`;
        clearTimeout(this.fieldTimers.get(key));
        this.fieldTimers.set(key, setTimeout(() => {
          this.fieldTimers.delete(key);
          this.updateField(itemId, name, this.fieldText(field), {updateDom: false, announce: false});
        }, 240));
      }

      handleFieldBlur(event) {
        const field = event.target.closest?.("[data-author-field]");
        if (!field) return;
        const itemId = field.closest("[data-author-item-id]")?.dataset.authorItemId;
        const name = field.dataset.authorField;
        const key = `${itemId}:${name}`;
        if (!this.fieldTimers.has(key)) return;
        clearTimeout(this.fieldTimers.get(key));
        this.fieldTimers.delete(key);
        this.updateField(itemId, name, this.fieldText(field), {updateDom: false, announce: false});
      }

      fieldText(field) {
        return String(field.innerText || field.textContent || "").replace(/\u00a0/g, " ").replace(/\n{3,}/g, "\n\n").trim();
      }

      handlePaste(event) {
        if (!this.active) return;
        const field = event.target.closest?.("[data-author-field]");
        const files = [...(event.clipboardData?.files || [])].filter(file => file.type.startsWith("image/"));
        if (files.length) {
          event.preventDefault();
          event.stopPropagation();
          this.requestMediaImport(files, this.importContext(event.target, "paste"));
          return;
        }
        if (!field) return;
        const text = event.clipboardData?.getData("text/plain");
        if (typeof text !== "string") return;
        event.preventDefault();
        event.stopPropagation();
        this.insertPlainText(text);
      }

      insertPlainText(text) {
        const selection = getSelection();
        if (!selection?.rangeCount) return;
        const range = selection.getRangeAt(0);
        range.deleteContents();
        const node = document.createTextNode(text);
        range.insertNode(node);
        range.setStartAfter(node);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
        node.parentElement?.dispatchEvent(new InputEvent("input", {bubbles: true, inputType: "insertText", data: text}));
      }

      handleStageDragOver(event) {
        if (!this.active || ![...(event.dataTransfer?.items || [])].some(item => item.kind === "file" && item.type.startsWith("image/"))) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }

      handleStageDrop(event) {
        if (!this.active) return;
        const files = [...(event.dataTransfer?.files || [])].filter(file => file.type.startsWith("image/"));
        if (!files.length) return;
        event.preventDefault();
        event.stopPropagation();
        this.requestMediaImport(files, this.importContext(event.target, "drop"));
      }

      importContext(target, source) {
        const currentSlideId = this.currentSlideId();
        const node = target.closest?.("[data-author-item-id]");
        const selected = node?.dataset.authorItemId || this.selectedId;
        const candidate = this.items.get(selected);
        const selectedItem = candidate?.slideId === currentSlideId ? candidate : null;
        return {
          source,
          slideId: selectedItem?.slideId || currentSlideId,
          targetItemId: ContentAuthoring.mediaKinds.has(selectedItem?.kind) ? selectedItem.id : null,
          intent: ContentAuthoring.mediaKinds.has(selectedItem?.kind) ? "replace" : "append"
        };
      }

      requestMediaImport(files, context) {
        const detail = {
          files,
          context,
          response: null,
          respondWith(promise) { this.response = Promise.resolve(promise); }
        };
        this.dispatch("media-import-request", detail, {cancelable: true});
        const response = this.mediaImporter?.importFiles
          ? Promise.resolve(this.mediaImporter.importFiles(files, context, this))
          : (detail.response || this.importRasterFiles(files, context));
        if (!response) {
          this.setStatus("尚未连接媒体导入桥；图片没有插入文字 DOM。", "warning");
          return;
        }
        response.then(result => {
          if (Array.isArray(result?.pendingAssets)) result.pendingAssets.forEach(asset => this.registerPendingAsset(asset));
          this.dispatch("media-imported", {context, result});
        }).catch(error => this.reportError(error, "图片导入失败"));
      }

      async importRasterFiles(files, context = {}) {
        const accepted = [];
        const targetSlideId = context.slideId || this.currentSlideId();
        let replaceTarget = context.intent === "replace" ? context.targetItemId : null;
        for (const file of files) {
          const raster = await this.validateRasterFile(file);
          const assetId = this.createId("asset");
          const relativePath = `assets/authoring/${this.safeAssetName(file.name, raster.mime)}`;
          this.registerPendingAsset({assetId, blob: file, mime: raster.mime, relativePath});
          const preview = await this.dataUrl(file);
          const replacement = this.items.get(replaceTarget);
          const selectResult = targetSlideId === this.currentSlideId();
          if (replaceTarget && replacement?.slideId === targetSlideId && ContentAuthoring.mediaKinds.has(replacement.kind)) {
            this.replaceMediaItem(replaceTarget, {
              assetId,
              sourcePath: relativePath,
              alt: this.assetLabel(file.name),
              caption: this.items.get(replaceTarget).caption || this.assetLabel(file.name),
              preview,
              width: raster.width,
              height: raster.height
            }, {select: selectResult});
            accepted.push({itemId: replaceTarget, assetId, replacement: true});
            replaceTarget = null;
          } else {
            const itemId = this.appendMediaItem(targetSlideId, {
              assetId,
              sourcePath: relativePath,
              alt: this.assetLabel(file.name),
              caption: this.assetLabel(file.name),
              preview,
              width: raster.width,
              height: raster.height
            }, {select: selectResult});
            accepted.push({itemId, assetId, replacement: false});
          }
        }
        this.setStatus(`已导入 ${accepted.length} 张图片；Blob 只保存在当前会话，建议立即保存。`, "dirty");
        return {items: accepted, pendingAssets: []};
      }

      async validateRasterFile(file) {
        if (!(file instanceof Blob)) throw new Error("没有可读取的图片文件");
        if (file.size > 8 * 1024 * 1024) throw new Error("单张图片不能超过 8 MB");
        const declared = String(file.type || "").toLowerCase();
        const allowed = new Set(["image/png", "image/jpeg", "image/webp"]);
        if (declared && !allowed.has(declared)) throw new Error("仅支持 PNG、JPEG 或 WebP");
        const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer());
        const png = bytes.length >= 8 && [0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a].every((byte, index) => bytes[index] === byte);
        const jpeg = bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
        const webp = bytes.length >= 12 && String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" && String.fromCharCode(...bytes.slice(8, 12)) === "WEBP";
        const mime = png ? "image/png" : jpeg ? "image/jpeg" : webp ? "image/webp" : "";
        if (!mime || (declared && declared !== mime)) throw new Error("图片内容与文件类型不匹配");
        const dimensions = await this.decodeRasterDimensions(file);
        if (dimensions.width > 12000 || dimensions.height > 12000 || dimensions.width * dimensions.height > 40_000_000) {
          throw new Error("图片像素尺寸过大（上限 12000 px / 4000 万像素）");
        }
        return {mime, ...dimensions};
      }

      async decodeRasterDimensions(blob) {
        if (typeof createImageBitmap === "function") {
          let bitmap;
          try {
            bitmap = await createImageBitmap(blob);
            if (!bitmap.width || !bitmap.height) throw new Error("图片尺寸无效");
            return {width: bitmap.width, height: bitmap.height};
          } catch (_) {
            throw new Error("图片无法解码");
          } finally {
            bitmap?.close?.();
          }
        }
        const url = URL.createObjectURL(blob);
        try {
          return await new Promise((resolve, reject) => {
            const image = new Image();
            image.addEventListener("load", () => resolve({width: image.naturalWidth, height: image.naturalHeight}), {once: true});
            image.addEventListener("error", () => reject(new Error("图片无法解码")), {once: true});
            image.src = url;
          });
        } finally {
          URL.revokeObjectURL(url);
        }
      }

      safeAssetName(name, mime) {
        const extension = {"image/png":"png", "image/jpeg":"jpg", "image/webp":"webp"}[mime] || "bin";
        const stem = String(name || "image").replace(/\.[^.]+$/, "").replace(/[^0-9A-Za-z._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "").slice(0, 80) || "image";
        return `${stem}.${extension}`;
      }

      assetLabel(name) {
        return String(name || "演示图片").replace(/\.[^.]+$/, "").trim() || "演示图片";
      }

      replaceMediaItem(itemId, values, options = {}) {
        const item = this.items.get(itemId);
        if (!item || !ContentAuthoring.mediaKinds.has(item.kind)) throw new Error("所选内容不是可替换媒体");
        const oldNode = this.nodes.get(itemId);
        item.kind = "image";
        item.assetId = String(values.assetId || "");
        item.sourcePath = String(values.sourcePath || "");
        item.alt = String(values.alt || item.alt || "演示图片");
        item.caption = String(values.caption ?? item.caption ?? "");
        item.width = Number(values.width) || null;
        item.height = Number(values.height) || null;
        item.dirtyFields.add("source");
        item.dirtyFields.add("alt");
        item.dirtyFields.add("caption");
        const node = this.createMediaNode(item, values.preview || "");
        this.widgetManager?.unregister?.(oldNode);
        oldNode?.replaceWith(node);
        this.nodes.set(itemId, node);
        this.markContentChanged(this.slideStates.get(item.slideId));
        this.commitMutation({op: "replace-media", itemId, baseHash: item.baseHash, item: this.itemSnapshot(item)}, [item.slideId], options);
        if (options.select !== false) this.select(itemId, {force: true});
        return itemId;
      }

      appendMediaItem(slideId, values, options = {}) {
        const state = this.requireContentSlide(slideId);
        if (this.hasSpecializedItems(state)) {
          const error = new Error("包含表格、代码或图表的专用布局页暂不支持追加图片");
          error.code = "UNSUPPORTED_SLIDE";
          throw error;
        }
        const item = {
          id: options.id || this.createId("image"),
          kind: "image",
          slideId,
          title: "",
          body: "",
          caption: String(values.caption || ""),
          alt: String(values.alt || "演示图片"),
          calloutKind: "",
          markdown: "",
          baseHash: "",
          sourceRange: null,
          fieldRanges: {},
          assetId: String(values.assetId || ""),
          sourcePath: String(values.sourcePath || ""),
          width: Number(values.width) || null,
          height: Number(values.height) || null,
          created: true,
          dirtyFields: new Set(["source", "alt", "caption"])
        };
        this.items.set(item.id, item);
        this.nodes.set(item.id, this.createMediaNode(item, values.preview || ""));
        this.insertInLane(state, item.id, null);
        this.markContentChanged(state);
        this.commitMutation({op: "add-media", slideId, item: this.itemSnapshot(item)}, [slideId], options);
        if (options.select !== false) this.select(item.id, {force: true});
        return item.id;
      }

      createMediaNode(item, preview) {
        const figure = document.createElement("figure");
        figure.className = "card media-figure visual-widget";
        figure.dataset.authorItemId = item.id;
        figure.dataset.authorItemKind = "image";
        figure.dataset.authorBaseHash = item.baseHash || "";
        figure.dataset.visualWidget = "image";
        figure.tabIndex = 0;
        const content = document.createElement("div");
        content.className = "visual-widget-content";
        content.dataset.visualContent = "";
        const image = document.createElement("img");
        image.src = preview;
        image.alt = item.alt;
        image.draggable = false;
        image.style.objectFit = "contain";
        content.appendChild(image);
        figure.appendChild(content);
        if (item.caption) {
          const caption = document.createElement("figcaption");
          caption.dataset.authorField = "caption";
          caption.textContent = item.caption;
          figure.appendChild(caption);
        }
        if (this.active) this.makeItemFieldsEditable(figure);
        return figure;
      }

      handlePanelClick(event) {
        const gallery = event.target.closest("[data-author-gallery-display]");
        if (gallery) {
          this.setGalleryDisplay(this.currentSlideId(), gallery.dataset.authorGalleryDisplay);
          return;
        }
        const target = event.target.closest("[data-author-action]");
        if (!target) return;
        const action = target.dataset.authorAction;
        if (action === "toggle-mode") this.setActive(!this.active);
        else if (action === "add-text") this.addTextBlock(this.currentSlideId());
        else if (action === "add-callout") this.addCallout(this.currentSlideId());
        else if (action === "upload-image") this.imageInput?.click();
        else if (action === "move-prev") this.moveSelected(-1);
        else if (action === "move-next") this.moveSelected(1);
        else if (action === "select") this.select(target.closest("[data-author-order-item]")?.dataset.authorOrderItem);
        else if (action === "order-up") this.reorderByDelta(target.closest("[data-author-order-item]")?.dataset.authorOrderItem, -1);
        else if (action === "order-down") this.reorderByDelta(target.closest("[data-author-order-item]")?.dataset.authorOrderItem, 1);
        else if (action === "show-new-chapter") this.showChapterCreator();
        else if (action === "add-chapter") this.addChapterFromInput();
        else if (action === "save") void this.save();
      }

      handlePanelChange(event) {
        if (event.target.matches("[data-author-image-input]")) {
          const files = [...(event.target.files || [])];
          if (files.length) this.requestMediaImport(files, this.importContext(this.nodes.get(this.selectedId) || this.stage, "upload"));
          event.target.value = "";
          return;
        }
        if (event.target.matches("[data-author-chapter-select]")) {
          try {
            this.setChapterItem(this.currentSlideId(), event.target.value);
          } catch (error) {
            this.reportError(error, "Chapter item 更新失败");
            this.refreshPanel();
          }
          return;
        }
        const input = event.target.closest("[data-author-input]");
        if (!input || !this.selectedId) return;
        this.updateField(this.selectedId, input.dataset.authorInput, input.value);
      }

      showChapterCreator() {
        if (!this.chapterCreate || !this.chapterInput) return;
        this.chapterCreate.hidden = false;
        this.chapterInput.value = "";
        this.chapterInput.focus();
      }

      addChapterFromInput() {
        if (!this.chapterInput || this.chapterCreate?.hidden) return false;
        try {
          const value = this.normalizeChapterName(this.chapterInput.value, {allowEmpty: false});
          this.setChapterItem(this.currentSlideId(), value);
          this.chapterInput.value = "";
          this.chapterCreate.hidden = true;
          return true;
        } catch (error) {
          this.reportError(error, "Chapter item 新增失败");
          this.chapterInput.focus();
          return false;
        }
      }

      handleOrderDragStart(event) {
        const row = event.target.closest("[data-author-order-item]");
        if (!row) return;
        this.draggedOrderId = row.dataset.authorOrderItem;
        row.classList.add("is-dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", this.draggedOrderId);
      }

      handleOrderDragOver(event) {
        if (!this.draggedOrderId) return;
        const row = event.target.closest("[data-author-order-item]");
        if (!row || row.dataset.authorOrderItem === this.draggedOrderId) return;
        event.preventDefault();
        const bounds = row.getBoundingClientRect();
        const before = event.clientY < bounds.top + bounds.height / 2;
        this.orderList.querySelectorAll(".drop-before,.drop-after").forEach(node => node.classList.remove("drop-before", "drop-after"));
        row.classList.add(before ? "drop-before" : "drop-after");
        this.orderDrop = {rowId: row.dataset.authorOrderItem, before};
      }

      handleOrderDrop(event) {
        if (!this.draggedOrderId || !this.orderDrop) return;
        event.preventDefault();
        const state = this.slideStates.get(this.currentSlideId());
        const lane = this.blockItemIds(state);
        const targetIndex = lane.indexOf(this.orderDrop.rowId);
        const beforeItemId = this.orderDrop.before ? this.orderDrop.rowId : (lane[targetIndex + 1] || null);
        this.reorderItem(state.id, this.draggedOrderId, beforeItemId);
        this.clearOrderDrag();
      }

      clearOrderDrag() {
        this.orderList?.querySelectorAll(".is-dragging,.drop-before,.drop-after")
          .forEach(node => node.classList.remove("is-dragging", "drop-before", "drop-after"));
        this.draggedOrderId = null;
        this.orderDrop = null;
      }

      currentSlideId() {
        const slide = this.presentation?.slides?.[this.presentation.current] || this.stage.querySelector(".slide.active");
        return slide?.dataset.slideId || this.slideStates.keys().next().value || null;
      }

      onSlideChange() {
        const currentSlideId = this.currentSlideId();
        const selected = this.items.get(this.selectedId);
        if (selected && selected.slideId !== currentSlideId) this.select(null);
        else this.refreshPanel();
        if (this.chapterCreate && !this.chapterCreate.hidden) {
          this.chapterCreate.hidden = true;
          if (this.chapterInput) this.chapterInput.value = "";
        }
      }

      chapterItemsForSlide(slideId) {
        const state = this.slideStates.get(slideId);
        if (!state?.section) return [];
        const seen = new Set();
        const items = [];
        [...this.slideStates.values()]
          .sort((left, right) => left.index - right.index)
          .forEach(candidate => {
            if (candidate.section !== state.section) return;
            const title = candidate.chapter || candidate.title;
            if (!title || seen.has(title)) return;
            seen.add(title);
            items.push({title, page: candidate.number, slideId: candidate.id});
          });
        return items;
      }

      normalizeChapterName(value, options = {}) {
        const source = String(value ?? "");
        if (/[\r\n\v\f\x1c-\x1e\u0085\u2028\u2029]/.test(source)) throw new Error("Chapter item 名称必须为单行文字");
        const normalized = source.trim();
        if (!normalized && options.allowEmpty === false) throw new Error("请输入 Chapter item 名称");
        if (normalized.length > 80) throw new Error("Chapter item 名称不能超过 80 个字符");
        if (/<!--|-->/.test(normalized)) throw new Error("Chapter item 名称不能包含 HTML 注释边界");
        return normalized;
      }

      setChapterItem(slideId, value, options = {}) {
        const state = this.requireContentSlide(slideId);
        if (!state.section) throw new Error("当前演示文稿没有可用的 Section，无法设置 Chapter item");
        const chapter = this.normalizeChapterName(value);
        if (state.chapter === chapter) return true;
        state.chapter = chapter;
        state.chapterChanged = state.chapter !== state.baseChapter;
        if (chapter) state.config.chapter = chapter;
        else delete state.config.chapter;
        state.element.dataset.chapter = chapter;
        state.changed = state.contentChanged || state.chapterChanged;
        this.commitMutation(
          {op: "set-chapter", slideId, chapter},
          [slideId],
          {...options, reconcile: false}
        );
        return true;
      }

      select(itemId, options = {}) {
        const next = itemId && this.items.has(itemId) && ContentAuthoring.movableKinds.has(this.items.get(itemId).kind) ? itemId : null;
        if (next === this.selectedId && !options.force) return;
        this.nodes.get(this.selectedId)?.classList.remove("is-author-selected");
        this.nodes.get(this.selectedId)?.removeAttribute("aria-selected");
        this.selectedId = next;
        const node = this.nodes.get(next);
        node?.classList.add("is-author-selected");
        node?.setAttribute("aria-selected", "true");
        this.dispatch("selection-change", {item: next ? this.itemSnapshot(this.items.get(next)) : null});
        this.refreshPanel();
        if (options.focusPanel) this.panel?.querySelector(`[data-author-order-item="${next}"] [data-author-action="select"]`)?.focus();
      }

      addTextBlock(slideId = this.currentSlideId(), values = {}, options = {}) {
        return this.addBlock("text", slideId, {
          title: values.title ?? "标题",
          body: values.body ?? "正文"
        }, options);
      }

      addCallout(slideId = this.currentSlideId(), values = {}, options = {}) {
        return this.addBlock("callout", slideId, {
          title: values.title ?? "补充说明",
          body: values.body ?? "正文",
          calloutKind: values.calloutKind || "note"
        }, options);
      }

      addBlock(kind, slideId, values, options = {}) {
        const state = this.requireContentSlide(slideId);
        const item = {
          id: options.id || this.createId(kind),
          kind,
          slideId,
          title: String(values.title || ""),
          body: String(values.body || ""),
          caption: "",
          alt: "",
          calloutKind: String(values.calloutKind || "note").toLowerCase(),
          markdown: "",
          baseHash: "",
          sourceRange: null,
          fieldRanges: {},
          assetId: "",
          sourcePath: "",
          created: true,
          dirtyFields: new Set(["title", "body"])
        };
        this.items.set(item.id, item);
        const node = this.createBlockNode(item);
        this.nodes.set(item.id, node);
        const selected = this.items.get(this.selectedId);
        const beforeItemId = selected?.slideId === slideId && ContentAuthoring.blockKinds.has(selected.kind)
          ? this.nextLaneItemId(state, selected.id)
          : null;
        this.insertInLane(state, item.id, beforeItemId);
        this.markContentChanged(state);
        this.commitMutation({op: "add", slideId, beforeItemId, item: this.itemSnapshot(item)}, [slideId], options);
        if (options.select !== false) this.select(item.id);
        return item.id;
      }

      createBlockNode(item) {
        const node = document.createElement("article");
        node.dataset.authorItemId = item.id;
        node.dataset.authorItemKind = item.kind;
        node.dataset.authorBaseHash = "";
        node.dataset.presenterFocus = "";
        if (item.kind === "callout") {
          node.className = `card soft text-card callout-card callout-${this.safeCalloutKind(item.calloutKind)}`;
          const title = document.createElement("strong");
          title.dataset.authorField = "title";
          title.textContent = item.title;
          const body = document.createElement("p");
          body.dataset.authorField = "body";
          body.textContent = item.body;
          node.append(title, body);
        } else {
          node.className = "card text-card section-card";
          const title = document.createElement("h3");
          title.dataset.authorField = "title";
          title.textContent = item.title;
          const body = document.createElement("div");
          body.dataset.authorField = "body";
          const paragraph = document.createElement("p");
          paragraph.textContent = item.body;
          body.appendChild(paragraph);
          node.append(title, body);
        }
        if (this.active) this.makeItemFieldsEditable(node);
        return node;
      }

      safeCalloutKind(value) {
        return ["tip", "note", "warning", "quote", "question"].includes(value) ? value : "note";
      }

      makeItemFieldsEditable(node) {
        node.querySelectorAll("[data-author-field]").forEach(field => {
          field.setAttribute("contenteditable", "plaintext-only");
          field.setAttribute("spellcheck", "true");
          field.dataset.authorEditKey = `${node.dataset.authorItemId}:${field.dataset.authorField}`;
        });
      }

      updateField(itemId, field, value, options = {}) {
        const item = this.items.get(itemId);
        if (!item || !["title", "body", "caption"].includes(field)) return false;
        const normalized = String(value ?? "").replace(/\r\n/g, "\n");
        if (item[field] === normalized) return true;
        item[field] = normalized;
        item.dirtyFields.add(field);
        this.markContentChanged(this.slideStates.get(item.slideId));
        if (options.updateDom !== false) this.writeField(this.nodes.get(itemId), item, field, normalized);
        this.commitMutation({op: "update-field", itemId, field, value: normalized, baseHash: item.baseHash}, [item.slideId], options);
        return true;
      }

      writeField(node, item, field, value) {
        const target = node?.querySelector(`[data-author-field="${field}"]`);
        if (!target) return;
        if (item.kind === "text" && field === "body" && target.tagName === "DIV") {
          target.replaceChildren(Object.assign(document.createElement("p"), {textContent: value}));
        } else target.textContent = value;
      }

      reorderItem(slideId, itemId, beforeItemId = null, options = {}) {
        const state = this.slideStates.get(slideId);
        const item = this.items.get(itemId);
        if (!state || !item || item.slideId !== slideId || !ContentAuthoring.blockKinds.has(item.kind)) return false;
        if (beforeItemId) {
          const before = this.items.get(beforeItemId);
          if (!before || before.slideId !== slideId || !ContentAuthoring.blockKinds.has(before.kind)) return false;
        }
        const previous = [...state.itemIds];
        const lane = this.blockItemIds(state).filter(id => id !== itemId);
        const insertion = beforeItemId ? lane.indexOf(beforeItemId) : lane.length;
        lane.splice(insertion < 0 ? lane.length : insertion, 0, itemId);
        let laneIndex = 0;
        state.itemIds = state.itemIds.map(id => ContentAuthoring.blockKinds.has(this.items.get(id)?.kind)
          ? lane[laneIndex++]
          : id);
        if (previous.join("\0") === state.itemIds.join("\0")) return true;
        this.markContentChanged(state);
        this.commitMutation({op: "reorder", slideId, itemId, beforeItemId}, [slideId], options);
        this.select(itemId, {force: true});
        return true;
      }

      reorderByDelta(itemId, delta) {
        const item = this.items.get(itemId);
        const state = this.slideStates.get(item?.slideId);
        if (!item || !state || !ContentAuthoring.blockKinds.has(item.kind)) return false;
        const lane = this.blockItemIds(state);
        const index = lane.indexOf(itemId);
        const target = index + delta;
        if (index < 0 || target < 0 || target >= lane.length) return false;
        const beforeItemId = delta < 0 ? lane[target] : (lane[target + 1] || null);
        return this.reorderItem(state.id, itemId, beforeItemId);
      }

      moveSelected(delta) {
        if (!this.selectedId || ![-1, 1].includes(delta)) return false;
        const item = this.items.get(this.selectedId);
        const source = this.slideStates.get(item?.slideId);
        const slides = [...this.slideStates.values()].sort((left, right) => left.index - right.index);
        const target = slides[source.index + delta];
        if (!target || target.kind !== "content") return false;
        return this.moveItem(item.id, target.id, null, {navigate: true});
      }

      moveItem(itemId, targetSlideId, beforeItemId = null, options = {}) {
        const item = this.items.get(itemId);
        const source = this.slideStates.get(item?.slideId);
        const target = this.requireContentSlide(targetSlideId);
        if (!item || !source || !ContentAuthoring.movableKinds.has(item.kind) || source.id === target.id) return false;
        if (ContentAuthoring.mediaKinds.has(item.kind) && this.hasSpecializedItems(target)) {
          this.setStatus("包含表格、代码或图表的专用布局页暂不接收新增图片。", "warning");
          return false;
        }
        if (beforeItemId) {
          const before = this.items.get(beforeItemId);
          if (!before || before.slideId !== target.id || this.laneFor(before.kind) !== this.laneFor(item.kind)) return false;
        }
        source.itemIds = source.itemIds.filter(id => id !== itemId);
        const fromSlideId = source.id;
        item.slideId = target.id;
        this.insertInLane(target, itemId, beforeItemId);
        this.markContentChanged(source);
        this.markContentChanged(target);
        this.commitMutation({op: "move", itemId, fromSlideId, toSlideId: target.id, beforeItemId}, [source.id, target.id], options);
        if (options.navigate !== false) {
          const targetIndex = [...this.slideStates.values()].sort((left, right) => left.index - right.index).findIndex(slide => slide.id === target.id);
          this.presentation?.show?.(targetIndex, false);
        }
        this.select(itemId, {force: true});
        return true;
      }

      setGalleryDisplay(slideId, display, options = {}) {
        const state = this.slideStates.get(slideId);
        const normalized = display === "tabs" ? "tabs" : "grid";
        if (!state || this.hasSpecializedItems(state) || this.mediaItemIds(state).length < 2) return false;
        if (state.galleryDisplay === normalized) return true;
        state.galleryDisplay = normalized;
        state.galleryChanged = true;
        this.markContentChanged(state);
        this.commitMutation({op: "set-gallery-display", slideId, display: normalized}, [slideId], options);
        return true;
      }

      insertInLane(state, itemId, beforeItemId) {
        const item = this.items.get(itemId);
        const lane = this.laneFor(item?.kind);
        state.itemIds = state.itemIds.filter(id => id !== itemId);
        if (beforeItemId) {
          const index = state.itemIds.indexOf(beforeItemId);
          if (index >= 0) {
            state.itemIds.splice(index, 0, itemId);
            return;
          }
        }
        let insertion = -1;
        state.itemIds.forEach((id, index) => {
          if (this.laneFor(this.items.get(id)?.kind) === lane) insertion = index;
        });
        state.itemIds.splice(insertion + 1, 0, itemId);
      }

      markContentChanged(state) {
        if (!state) return;
        state.contentChanged = true;
        state.changed = true;
      }

      laneFor(kind) {
        if (ContentAuthoring.mediaKinds.has(kind)) return "media";
        if (ContentAuthoring.blockKinds.has(kind)) return "block";
        return `fixed:${kind}`;
      }

      nextLaneItemId(state, itemId) {
        const item = this.items.get(itemId);
        const lane = this.laneFor(item?.kind);
        const index = state.itemIds.indexOf(itemId);
        return state.itemIds.slice(index + 1).find(id => this.laneFor(this.items.get(id)?.kind) === lane) || null;
      }

      blockItemIds(state) {
        return state?.itemIds.filter(id => ContentAuthoring.blockKinds.has(this.items.get(id)?.kind)) || [];
      }

      mediaItemIds(state) {
        return state?.itemIds.filter(id => ContentAuthoring.mediaKinds.has(this.items.get(id)?.kind)) || [];
      }

      hasSpecializedItems(state) {
        return Boolean(state?.itemIds.some(id => ["table", "code", "chart", "mermaid", "excalidraw", "archscribe"].includes(this.items.get(id)?.kind)));
      }

      requireContentSlide(slideId) {
        const state = this.slideStates.get(slideId);
        if (!state || state.kind !== "content") {
          const error = new Error("结构页不支持新增或接收内容项");
          error.code = "UNSUPPORTED_SLIDE";
          throw error;
        }
        return state;
      }

      createId(kind) {
        const random = globalThis.crypto?.randomUUID?.().replaceAll("-", "") || `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
        let id = `${kind}-${random.slice(0, 20)}`;
        while (this.items.has(id)) id = `${kind}-${random.slice(0, 16)}-${Math.random().toString(36).slice(2, 6)}`;
        return id;
      }

      commitMutation(operation, slideIds, options = {}) {
        const affected = [...new Set(slideIds.filter(Boolean))];
        if (options.reconcile !== false) this.reconcileSlides(affected);
        if (options.record === false) return;
        this.revision += 1;
        const record = {...operation, revision: this.revision};
        const previous = this.operations[this.operations.length - 1];
        if (record.op === "set-chapter") {
          this.operations = this.operations.filter(candidate => candidate.op !== "set-chapter" || candidate.slideId !== record.slideId);
          if (this.slideStates.get(record.slideId)?.chapterChanged) this.operations.push(record);
        } else if (record.op === "update-field" && previous?.op === "update-field" && previous.itemId === record.itemId && previous.field === record.field) {
          this.operations[this.operations.length - 1] = record;
        } else this.operations.push(record);
        this.dirty = this.operations.length > 0;
        if (this.dirty) this.persistDraft();
        else {
          this.revision = 0;
          this.clearDraft();
        }
        this.dispatch("change", {revision: this.revision, operation: record, affectedSlideIds: affected, dirty: this.dirty});
        this.refreshPanel();
        if (options.announce !== false) this.setStatus(
          this.dirty ? "改动已暂存在本机；点击“保存改动”写回源文件。" : "已恢复到构建时状态。",
          this.dirty ? "dirty" : "clean"
        );
      }

      reconcileSlides(slideIds) {
        slideIds.forEach(slideId => {
          const state = this.slideStates.get(slideId);
          if (!state) return;
          const snapshot = this.slideSnapshot(state);
          let handled = false;
          try {
            handled = this.domBridge?.reconcileSlide?.({slide: state.element, state: snapshot, nodes: this.nodes, feature: this}) === true;
            if (!handled) handled = this.layoutEditor?.reconcileAuthoringSlide?.(state.element, snapshot, {nodes: this.nodes}) === true;
          } catch (error) {
            this.reportError(error, "页面内容重排失败");
          }
          if (!handled) this.fallbackReconcileDom(state);
          this.updateSlideMetrics(state);
          this.widgetManager?.reconcile?.(state.element);
          this.mediaTabsManager?.reconcile?.(state.element);
          this.mediaPlayback?.reconcile?.(state.element);
          this.mediaPlayback?.sync?.();
          this.layoutEditor?.onAuthoringContentChange?.(state.element, snapshot);
        });
        requestAnimationFrame(() => {
          if (typeof inspectSlides === "function") inspectSlides();
        });
        this.dispatch("structure-change", {slideIds});
      }

      fallbackReconcileDom(state) {
        const slide = state.element;
        const content = slide.querySelector(":scope > .content");
        if (!content || state.kind !== "content") return;
        const items = state.itemIds.map(id => this.items.get(id)).filter(Boolean);
        const specialized = this.hasSpecializedItems(state);
        if (specialized) {
          const table = slide.querySelector(".table-layout");
          const chartCopy = slide.querySelector(".chart-copy");
          const copy = table || chartCopy || slide.querySelector(".split-copy,.gallery-copy,.wide-copy,.text-grid");
          const visualKinds = new Set(["chart", "mermaid", "excalidraw", "archscribe"]);
          const ids = state.itemIds.filter(id => {
            const kind = this.items.get(id)?.kind;
            if (ContentAuthoring.mediaKinds.has(kind)) return false;
            return !chartCopy || !visualKinds.has(kind);
          });
          if (copy) ids.forEach(id => {
            const node = this.nodes.get(id);
            if (node) copy.appendChild(node);
          });
          return;
        }
        const mediaIds = this.mediaItemIds(state);
        const blockIds = state.itemIds.filter(id => !ContentAuthoring.mediaKinds.has(this.items.get(id)?.kind));
        const mediaNodes = mediaIds.map(id => this.nodes.get(id)).filter(Boolean);
        const blockNodes = blockIds.map(id => this.nodes.get(id)).filter(Boolean);
        const layout = mediaNodes.length >= 2 ? "gallery"
          : mediaNodes.length === 1 && blockNodes.length ? "split"
          : mediaNodes.length === 1 ? "media"
          : "text";
        let root;
        if (layout === "gallery") {
          root = document.createElement("div");
          root.className = `gallery-layout${blockNodes.length ? "" : " gallery-only"}`;
          const stage = document.createElement("div");
          stage.className = "gallery-stage";
          root.appendChild(stage);
          if (blockNodes.length) {
            const copy = this.createCopyLane("gallery-copy", blockNodes);
            root.appendChild(copy);
          }
          content.replaceChildren(root);
          this.rebuildGalleryStage(state, stage);
        } else if (layout === "split") {
          root = document.createElement("div");
          root.className = "split-layout landscape";
          const media = document.createElement("div");
          media.className = "split-media";
          media.appendChild(mediaNodes[0]);
          root.append(media, this.createCopyLane("split-copy", blockNodes));
          content.replaceChildren(root);
        } else if (layout === "media") {
          root = document.createElement("div");
          root.className = "wide-media-layout";
          const media = document.createElement("div");
          media.className = "wide-media-stage";
          media.appendChild(mediaNodes[0]);
          const copy = document.createElement("div");
          copy.className = "empty-copy";
          copy.setAttribute("aria-hidden", "true");
          root.append(media, copy);
          content.replaceChildren(root);
        } else {
          root = this.createCopyLane("text-grid", blockNodes);
          content.replaceChildren(root);
        }
        [...slide.classList].filter(name => name.startsWith("layout-")).forEach(name => slide.classList.remove(name));
        slide.classList.add(`layout-${layout}`);
        slide.dataset.layoutResolved = layout;
        if (state.layoutResolved !== layout) {
          state.layoutResolved = layout;
          state.layoutChanged = true;
        }
        if (layout === "gallery") state.galleryChanged = true;
      }

      createCopyLane(className, nodes) {
        const copy = document.createElement("div");
        copy.className = `${className} count-${Math.max(1, Math.min(7, nodes.length))}`;
        nodes.forEach(node => copy.appendChild(node));
        return copy;
      }

      rebuildGalleryStage(state, stage) {
        const mediaIds = this.mediaItemIds(state);
        const mediaNodes = mediaIds.map(id => this.nodes.get(id)).filter(Boolean);
        if (state.galleryDisplay === "tabs") {
          const shell = document.createElement("div");
          shell.className = "media-tabs";
          shell.dataset.mediaTabs = "";
          mediaNodes.forEach((node, index) => {
            node.dataset.mediaPanel = mediaIds[index];
            node.classList.toggle("active", index === 0);
            shell.appendChild(node);
          });
          const tabs = document.createElement("div");
          tabs.className = "media-tab-list";
          mediaIds.forEach((id, index) => {
            const item = this.items.get(id);
            const button = document.createElement("button");
            button.type = "button";
            button.dataset.mediaTarget = id;
            button.classList.toggle("active", index === 0);
            button.setAttribute("aria-label", `查看${item.caption || item.alt || index + 1}`);
            button.textContent = String(index + 1);
            tabs.appendChild(button);
          });
          shell.appendChild(tabs);
          stage.replaceChildren(shell);
          this.mediaTabsManager?.reconcile?.(shell);
          if (!this.mediaTabsManager && typeof MediaTabs === "function") new MediaTabs(shell);
        } else {
          const grid = document.createElement("div");
          grid.className = `media-grid count-${Math.min(4, mediaNodes.length)}`;
          mediaNodes.forEach(node => {
            delete node.dataset.mediaPanel;
            node.classList.remove("active");
            grid.appendChild(node);
          });
          stage.replaceChildren(grid);
        }
      }

      updateSlideMetrics(state) {
        const items = state.itemIds.map(id => this.items.get(id)).filter(Boolean);
        const blocks = items.filter(item => !ContentAuthoring.mediaKinds.has(item.kind));
        state.element.dataset.mediaCount = String(items.length - blocks.length);
        state.element.dataset.blockCount = String(blocks.length);
        state.element.dataset.textLength = String(blocks.reduce((sum, item) => sum + (item.title + item.body).replace(/\s+/g, "").length, 0));
        state.element.dataset.galleryDisplay = state.galleryDisplay;
      }

      slideSnapshot(state) {
        return {
          id: state.id,
          kind: state.kind,
          number: state.number,
          title: state.title,
          subtitle: state.subtitle,
          section: state.section,
          chapter: state.chapter,
          chapterChanged: state.chapterChanged,
          baseHash: state.baseHash,
          layoutResolved: state.layoutResolved,
          layoutChanged: state.layoutChanged,
          galleryDisplay: state.galleryDisplay,
          galleryChanged: state.galleryChanged,
          items: state.itemIds.map(id => this.itemSnapshot(this.items.get(id))).filter(Boolean)
        };
      }

      itemSnapshot(item) {
        if (!item) return null;
        return {
          id: item.id,
          kind: item.kind,
          slideId: item.slideId,
          title: item.title,
          body: item.body,
          caption: item.caption,
          alt: item.alt,
          calloutKind: item.calloutKind,
          markdown: item.markdown,
          baseHash: item.baseHash,
          sourceRange: item.sourceRange,
          fieldRanges: item.fieldRanges,
          assetId: item.assetId,
          sourcePath: item.sourcePath,
          width: item.width || null,
          height: item.height || null,
          created: item.created,
          dirtyFields: [...item.dirtyFields]
        };
      }

      snapshot() {
        return {
          schemaVersion: ContentAuthoring.schemaVersion,
          revision: this.revision,
          slides: [...this.slideStates.values()].sort((left, right) => left.index - right.index).map(state => this.slideSnapshot(state))
        };
      }

      buildChangeSet() {
        const layoutPayload = this.layoutEditor?.exportPayload?.() || this.manifest.layout || null;
        return {
          schemaVersion: ContentAuthoring.schemaVersion,
          base: {
            sourceName: this.source.name,
            sourceSha256: this.source.sha256,
            layoutName: this.layoutName(),
            layoutSha256: this.source.layoutSha256 || ""
          },
          revision: this.revision,
          operations: this.operations.map(operation => structuredClone(operation)),
          snapshot: this.snapshot(),
          layout: layoutPayload,
          pendingAssets: [...this.pendingAssets.values()].map(asset => ({
            assetId: asset.assetId,
            relativePath: asset.relativePath || "",
            mime: asset.mime || asset.blob?.type || "application/octet-stream",
            sha256: asset.sha256 || "",
            blob: asset.blob
          }))
        };
      }

      registerPendingAsset(asset) {
        if (!asset?.assetId || !(asset.blob instanceof Blob)) throw new Error("Pending asset requires assetId and Blob");
        this.pendingAssets.set(String(asset.assetId), {
          assetId: String(asset.assetId),
          blob: asset.blob,
          mime: String(asset.mime || asset.blob.type || "application/octet-stream"),
          relativePath: String(asset.relativePath || ""),
          sha256: String(asset.sha256 || "")
        });
      }

      async save() {
        const changeSet = this.buildChangeSet();
        this.dispatch("save-state", {state: "saving"});
        this.setStatus("正在校验并保存源文件…", "saving");
        try {
          let result;
          if (this.saveAdapter?.save) {
            result = await this.saveAdapter.save(changeSet, this);
          } else {
            const request = {
              changeSet,
              response: null,
              respondWith(promise) { this.response = Promise.resolve(promise); }
            };
            this.dispatch("save-request", request, {cancelable: true});
            if (request.response) result = await request.response;
            else if (typeof globalThis.showDirectoryPicker === "function") {
              const pickerPromise = globalThis.showDirectoryPicker({id: "golajah-slide-source", mode: "readwrite"});
              const directory = await pickerPromise;
              result = await this.saveToDirectory(directory, changeSet);
            } else {
              const error = new Error("当前浏览器不支持直接写回源目录");
              error.code = "UNSUPPORTED";
              throw error;
            }
          }
          if (!result || !["saved", "exported"].includes(result.status)) {
            throw this.saveError("WRITE_FAILED", "保存桥未返回可验证的保存结果");
          }
          if (result.status === "saved" && (!result.sourceSha256 || !Array.isArray(result.changedFiles))) {
            throw this.saveError("WRITE_FAILED", "保存桥未返回源文件指纹或改动文件清单");
          }
          this.finishSave(result);
          return result;
        } catch (error) {
          const normalized = this.normalizeSaveError(error);
          const exported = await this.exportEditBundle(normalized, changeSet);
          this.dispatch("save-state", {state: "exported", error: normalized, result: exported});
          this.setStatus(normalized.code === "USER_CANCELLED"
            ? "未获得目录写入授权，已导出可恢复编辑包。"
            : `未覆盖源文件；已导出可恢复编辑包（${normalized.code}）。`, "warning");
          return exported;
        }
      }

      async saveToDirectory(directoryHandle, changeSet = this.buildChangeSet()) {
        if (!directoryHandle?.getFileHandle) throw this.saveError("UNSUPPORTED", "无效的目录句柄");
        if (this.needsRebuild) throw this.saveError("SOURCE_CONFLICT", "上次保存后尚未重新构建 HTML，拒绝使用旧范围再次写回");
        await this.ensureWritePermission(directoryHandle);
        if (!changeSet.base.sourceSha256 || !this.source.text) {
          throw this.saveError("UNSUPPORTED", "HTML 缺少可校验的源文件指纹或无损源码模型");
        }
        const sourcePath = this.safeRelativePath(changeSet.base.sourceName);
        const sourceHandle = await this.fileHandleAt(directoryHandle, sourcePath, false);
        const sourceFile = await sourceHandle.getFile();
        const diskBytes = await sourceFile.arrayBuffer();
        const diskHash = await this.sha256(diskBytes);
        if (diskHash !== changeSet.base.sourceSha256) {
          throw this.saveError("SOURCE_CONFLICT", "slides.md 在构建后已发生变化，拒绝覆盖");
        }
        const embeddedHash = await this.sha256(new TextEncoder().encode(this.source.text));
        if (embeddedHash !== changeSet.base.sourceSha256) {
          throw this.saveError("SOURCE_CONFLICT", "HTML 内嵌源码与基准指纹不一致，拒绝序列化");
        }
        const layoutPath = this.safeRelativePath(changeSet.base.layoutName || this.layoutName());
        const previousLayout = await this.readOptionalFile(directoryHandle, layoutPath);
        const layoutExistedAtBuild = Boolean(changeSet.base.layoutSha256);
        if (layoutExistedAtBuild !== Boolean(previousLayout)) {
          throw this.saveError("SOURCE_CONFLICT", "布局 JSON 在构建后被新增或删除，拒绝覆盖");
        }
        if (layoutExistedAtBuild) {
          const diskLayoutHash = await this.sha256(previousLayout.bytes);
          if (diskLayoutHash !== changeSet.base.layoutSha256) {
            throw this.saveError("SOURCE_CONFLICT", "布局 JSON 在构建后已发生变化，拒绝覆盖");
          }
        }
        const assetPlan = await this.planAssets(changeSet.pendingAssets || []);
        const assetPaths = Object.fromEntries(assetPlan.map(asset => [asset.assetId, asset.path]));
        const markdown = this.serializeMarkdown(assetPaths);
        const markdownBytes = new TextEncoder().encode(markdown);
        const targetSourceHash = await this.sha256(markdownBytes);
        const layoutPayload = this.layoutPayload(changeSet.layout, targetSourceHash);
        const layoutBytes = new TextEncoder().encode(JSON.stringify(layoutPayload, null, 2) + "\n");
        const changedFiles = [];
        let layoutWritten = false;
        let sourceWritten = false;
        try {
          for (const asset of assetPlan) {
            const existing = await this.readOptionalFile(directoryHandle, asset.path);
            if (existing) {
              const existingHash = await this.sha256(existing.bytes);
              if (existingHash !== asset.sha256) throw this.saveError("INVALID_PATH", `资产路径已存在不同内容：${asset.path}`);
            } else {
              await this.writeFileAt(directoryHandle, asset.path, asset.bytes, true);
            }
            changedFiles.push({path: asset.path, kind: "asset", sha256: asset.sha256});
          }
          await this.writeFileAt(directoryHandle, layoutPath, layoutBytes, true);
          layoutWritten = true;
          await this.writeFileAt(directoryHandle, sourcePath, markdownBytes, false);
          sourceWritten = true;
          const verifiedSource = await this.readOptionalFile(directoryHandle, sourcePath);
          const verifiedLayout = await this.readOptionalFile(directoryHandle, layoutPath);
          if (!verifiedSource || await this.sha256(verifiedSource.bytes) !== targetSourceHash) throw this.saveError("WRITE_FAILED", "slides.md 写入后校验失败");
          const layoutHash = await this.sha256(layoutBytes);
          if (!verifiedLayout || await this.sha256(verifiedLayout.bytes) !== layoutHash) throw this.saveError("WRITE_FAILED", "布局 JSON 写入后校验失败");
          changedFiles.push({path: layoutPath, kind: "layout", sha256: layoutHash});
          changedFiles.push({path: sourcePath, kind: "source", sha256: targetSourceHash});
          return {status: "saved", sourceSha256: targetSourceHash, sourceText: markdown, changedFiles, needsRebuild: true};
        } catch (error) {
          if (sourceWritten) {
            try { await this.writeFileAt(directoryHandle, sourcePath, new Uint8Array(diskBytes), false); } catch (_) { /* best-effort rollback */ }
          }
          if (layoutWritten) {
            try {
              if (previousLayout) await this.writeFileAt(directoryHandle, layoutPath, previousLayout.bytes, true);
              else await this.removeFileAt(directoryHandle, layoutPath);
            } catch (_) { /* content-addressed assets remain safe; bundle records recovery data */ }
          }
          throw error;
        }
      }

      serializeMarkdown(assetPaths = {}) {
        if (this.serializeBridge) {
          const value = this.serializeBridge(this.snapshot(), {
            manifest: this.manifest,
            source: this.source,
            operations: this.operations,
            assetPaths
          });
          if (typeof value !== "string") throw this.saveError("UNSUPPORTED", "源码序列化桥没有返回 Markdown");
          return value;
        }
        if (!this.source.text || this.source.offsetEncoding !== "utf-16") {
          throw this.saveError("UNSUPPORTED", "缺少 UTF-16 源码范围，无法无损写回 Markdown");
        }
        const replacements = [];
        for (const state of this.slideStates.values()) {
          if (!state.changed) continue;
          if (!state.sourceRange) throw this.saveError("UNSUPPORTED", `页面 ${state.id} 缺少 sourceRange`);
          replacements.push({
            ...state.sourceRange,
            text: this.normalizeReplacementNewlines(this.serializeSlide(state, assetPaths))
          });
        }
        let result = this.source.text;
        replacements.sort((left, right) => right.start - left.start).forEach(replacement => {
          result = result.slice(0, replacement.start) + replacement.text + result.slice(replacement.end);
        });
        if (this.source.bom && !result.startsWith("\ufeff")) result = "\ufeff" + result;
        return result;
      }

      normalizeReplacementNewlines(value) {
        const normalized = String(value).replace(/\r\n|\r/g, "\n");
        if (this.source.newline === "\r\n") return normalized.replace(/\n/g, "\r\n");
        if (this.source.newline === "\r") return normalized.replace(/\n/g, "\r");
        return normalized;
      }

      serializeSlide(state, assetPaths) {
        const base = state.source || this.source.text.slice(state.sourceRange.start, state.sourceRange.end);
        const trailingWhitespace = /\s*$/.exec(base)?.[0] || "";
        const ranged = state.baseItemIds.map(id => this.items.get(id)).filter(item => item?.sourceRange && item.sourceRange.start >= state.sourceRange.start && item.sourceRange.end <= state.sourceRange.end);
        ranged.sort((left, right) => left.sourceRange.start - right.sourceRange.start);
        const firstStart = ranged.length ? ranged[0].sourceRange.start - state.sourceRange.start : base.length;
        const lastEnd = ranged.length ? ranged[ranged.length - 1].sourceRange.end - state.sourceRange.start : base.length;
        let header = base.slice(0, firstStart).replace(/\s+$/, "");
        const tail = base.slice(lastEnd);
        for (let index = 0; index < ranged.length - 1; index += 1) {
          const gapStart = ranged[index].sourceRange.end - state.sourceRange.start;
          const gapEnd = ranged[index + 1].sourceRange.start - state.sourceRange.start;
          if (base.slice(gapStart, gapEnd).trim()) throw this.saveError("UNSUPPORTED", `页面 ${state.id} 含未建模内容，拒绝重写`);
        }
        const directives = {};
        if (state.layoutChanged) directives.layout = state.layoutResolved;
        if (state.galleryChanged) directives["gallery-display"] = state.galleryDisplay;
        if (state.chapterChanged) directives.chapter = state.chapter || null;
        if (Object.keys(directives).length) header = this.writeSlideDirectives(header, directives);
        const body = state.itemIds.map(id => this.serializeItem(this.items.get(id), assetPaths)).filter(Boolean).join("\n\n");
        const serialized = header + (body ? "\n\n" + body : "") + (tail.trim() ? "\n\n" + tail.trimStart() : tail);
        return serialized.replace(/\s*$/, "") + trailingWhitespace;
      }

      serializeItem(item, assetPaths) {
        if (!item) return "";
        const raw = item.markdown || (item.sourceRange ? this.source.text.slice(item.sourceRange.start, item.sourceRange.end) : "");
        if (!item.created && !item.dirtyFields.size && raw) return raw.trim();
        if (item.kind === "text") {
          const heading = item.title ? `### ${this.singleLine(item.title)}` : "";
          return [heading, this.safeTextBody(item.body)].filter(Boolean).join("\n\n");
        }
        if (item.kind === "callout") {
          const marker = `> [!${this.safeCalloutKind(item.calloutKind).toUpperCase()}]${item.title ? ` ${this.singleLine(item.title)}` : ""}`;
          const body = String(item.body).replace(/\r\n|\r/g, "\n").split("\n").map(line => `> ${line}`).join("\n");
          return `${marker}\n${body}`.trim();
        }
        if (ContentAuthoring.mediaKinds.has(item.kind)) {
          const path = assetPaths[item.assetId] || item.sourcePath;
          if (!path && raw) return raw.trim();
          if (!path) throw this.saveError("UNSUPPORTED", `媒体 ${item.id} 缺少资产路径`);
          const alt = this.singleLine(item.alt || "演示图片").replaceAll("[", "（").replaceAll("]", "）");
          const safeCaption = this.singleLine(item.caption).replaceAll('"', "”");
          const caption = safeCaption ? ` "${safeCaption}"` : "";
          return `![${alt}](${path}${caption})`;
        }
        if (raw) return raw.trim();
        throw this.saveError("UNSUPPORTED", `内容项 ${item.id} 无法序列化`);
      }

      singleLine(value) {
        return String(value || "").replace(/\s+/g, " ").trim();
      }

      safeTextBody(value) {
        return String(value || "")
          .replace(/\r\n|\r/g, "\n")
          .split("\n")
          .map(line => /^\s*---\s*$/.test(line) ? "\\---" : line)
          .join("\n")
          .trim();
      }

      writeSlideDirectives(header, entries) {
        const directive = /<!--\s*slide\b[\s\S]*?-->/i.exec(header);
        if (!directive) {
          const authoredEntries = Object.entries(entries).filter(([, value]) => value !== null);
          if (!authoredEntries.length) return header;
          const leading = /^\s*/.exec(header)?.[0] || "";
          const lines = authoredEntries.map(([key, value]) => `${key}: ${this.directiveScalar(key, value)}`).join("\n");
          return `${leading}<!-- slide\n${lines}\n-->\n${header.slice(leading.length)}`;
        }
        const parsed = /^<!--\s*slide\b([\s\S]*?)-->$/i.exec(directive[0]);
        const body = String(parsed?.[1] || "").replace(/\r\n|\r/g, "\n");
        const lines = body.split("\n");
        while (lines.length && !lines[0].trim()) lines.shift();
        while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
        if (lines.length) lines[0] = lines[0].replace(/^[ \t]*:[ \t]*/, "");
        Object.entries(entries).forEach(([key, value]) => {
          const safeKey = String(key).replace(/[^a-z-]/g, "");
          if (!safeKey) return;
          const expression = new RegExp(`^([ \\t]*${safeKey}[ \\t]*:)[ \\t]*(.*)$`, "i");
          const matches = [];
          lines.forEach((line, index) => {
            const match = expression.exec(line);
            if (match) matches.push({index, prefix: match[1]});
          });
          if (value === null) {
            matches.reverse().forEach(match => lines.splice(match.index, 1));
          } else if (matches.length) {
            const [first, ...duplicates] = matches;
            lines[first.index] = `${first.prefix} ${this.directiveScalar(safeKey, value)}`;
            duplicates.reverse().forEach(match => lines.splice(match.index, 1));
          } else {
            lines.push(`${safeKey}: ${this.directiveScalar(safeKey, value)}`);
          }
        });
        const updated = `<!-- slide\n${lines.join("\n")}\n-->`;
        return header.slice(0, directive.index) + updated + header.slice(directive.index + directive[0].length);
      }

      directiveScalar(key, value) {
        const source = String(value ?? "");
        return key === "chapter" ? `"${source}"` : source;
      }

      layoutPayload(value, targetSourceHash) {
        const payload = value && typeof value === "object" ? structuredClone(value) : {schemaVersion: "1.0", slides: {}};
        if (!payload.slides || typeof payload.slides !== "object" || Array.isArray(payload.slides)) payload.slides = {};
        this.slideStates.forEach(state => {
          if (!state.layoutChanged) return;
          const legacyKey = `P${state.number}`;
          const entryKey = payload.slides[state.id] ? state.id : (payload.slides[legacyKey] ? legacyKey : "");
          if (!entryKey || typeof payload.slides[entryKey] !== "object") return;
          const entry = payload.slides[entryKey];
          if (entryKey !== state.id) {
            payload.slides[state.id] = entry;
            delete payload.slides[entryKey];
          }
          entry.layout = state.layoutResolved;
          const content = entry.regions?.content;
          if (this.layoutEditor?.presetRegions) {
            entry.regions = this.layoutEditor.presetRegions(state.element, state.layoutResolved, content || undefined);
          } else entry.regions = content ? {content: structuredClone(content)} : {};
        });
        payload.sourceHash = targetSourceHash;
        payload.source = this.source.name;
        return payload;
      }

      layoutName() {
        if (this.source.layoutName) return this.source.layoutName;
        return this.source.name.replace(/\.[^.\/]+$/, "") + ".layout.json";
      }

      async planAssets(assets) {
        const planned = [];
        for (const asset of assets) {
          if (!(asset.blob instanceof Blob)) continue;
          const bytes = new Uint8Array(await asset.blob.arrayBuffer());
          const sha256 = await this.sha256(bytes);
          if (asset.sha256 && asset.sha256 !== sha256) throw this.saveError("SOURCE_CONFLICT", `待保存资产 ${asset.assetId} 指纹不匹配`);
          const mime = String(asset.mime || asset.blob.type || "");
          const extension = {"image/png":"png", "image/jpeg":"jpg", "image/webp":"webp"}[mime];
          if (!extension) throw this.saveError("UNSUPPORTED", `不支持的图片类型：${mime || "unknown"}`);
          const requested = asset.relativePath ? this.safeRelativePath(asset.relativePath) : `assets/authoring/${asset.assetId}.${extension}`;
          const segments = requested.split("/");
          const original = segments.pop().replace(/[^0-9A-Za-z._-]+/g, "-").replace(/^[-.]+/, "") || `${asset.assetId}.${extension}`;
          const directory = segments.join("/") || "assets/authoring";
          const path = `${directory}/${sha256.slice(0, 16)}-${original}`;
          planned.push({assetId: String(asset.assetId), path, bytes, sha256, mime});
        }
        return planned;
      }

      safeRelativePath(value) {
        const source = String(value || "").replaceAll("\\", "/");
        if (!source || source.startsWith("/") || /^[A-Za-z]:/.test(source) || source.includes("\0")) {
          throw this.saveError("INVALID_PATH", `非法相对路径：${source || "(empty)"}`);
        }
        const parts = source.split("/");
        if (parts.some(part => !part || part === "." || part === "..")) throw this.saveError("INVALID_PATH", `非法相对路径：${source}`);
        return parts.join("/");
      }

      async ensureWritePermission(handle) {
        if (!handle.queryPermission || !handle.requestPermission) return;
        const options = {mode: "readwrite"};
        if (await handle.queryPermission(options) === "granted") return;
        if (await handle.requestPermission(options) !== "granted") throw this.saveError("PERMISSION_DENIED", "目录写入授权被拒绝");
      }

      async directoryAt(root, segments, create) {
        let directory = root;
        for (const segment of segments) directory = await directory.getDirectoryHandle(segment, {create});
        return directory;
      }

      async fileHandleAt(root, relativePath, create) {
        const parts = this.safeRelativePath(relativePath).split("/");
        const name = parts.pop();
        const directory = await this.directoryAt(root, parts, create);
        return directory.getFileHandle(name, {create});
      }

      async readOptionalFile(root, relativePath) {
        try {
          const handle = await this.fileHandleAt(root, relativePath, false);
          const file = await handle.getFile();
          return {handle, file, bytes: new Uint8Array(await file.arrayBuffer())};
        } catch (error) {
          if (error?.name === "NotFoundError") return null;
          throw error;
        }
      }

      async writeFileAt(root, relativePath, bytes, create) {
        const handle = await this.fileHandleAt(root, relativePath, create);
        const writable = await handle.createWritable({keepExistingData: false});
        try {
          await writable.write(bytes);
          await writable.close();
        } catch (error) {
          try { await writable.abort?.(); } catch (_) { /* noop */ }
          throw this.saveError("WRITE_FAILED", `无法写入 ${relativePath}`, error);
        }
      }

      async removeFileAt(root, relativePath) {
        const parts = this.safeRelativePath(relativePath).split("/");
        const name = parts.pop();
        const directory = await this.directoryAt(root, parts, false);
        await directory.removeEntry(name);
      }

      async sha256(value) {
        if (!globalThis.crypto?.subtle) throw this.saveError("UNSUPPORTED", "浏览器缺少 SHA-256 校验能力");
        const bytes = value instanceof ArrayBuffer
          ? value
          : ArrayBuffer.isView(value) ? value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) : value;
        const digest = await crypto.subtle.digest("SHA-256", bytes);
        return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
      }

      finishSave(result) {
        const status = result?.status || "saved";
        if (status === "saved") {
          this.operations = [];
          this.dirty = false;
          this.revision = 0;
          if (result.sourceSha256) this.source.sha256 = result.sourceSha256;
          this.needsRebuild = result.needsRebuild === true;
          this.clearDraft();
          if (this.needsRebuild) this.setActive(false);
        }
        this.dispatch("saved", result);
        this.dispatch("save-state", {state: status, result});
        this.setStatus(status === "saved"
          ? `源文件已保存${result.needsRebuild ? "；请重新运行构建以刷新 HTML 与 build.json。" : "。"}`
          : "改动已导出，源文件未被覆盖。", status);
        this.refreshPanel();
      }

      async exportEditBundle(error, changeSet = this.buildChangeSet()) {
        const assets = [];
        const assetPlan = await this.planAssets(changeSet.pendingAssets || []);
        const assetPaths = Object.fromEntries(assetPlan.map(asset => [asset.assetId, asset.path]));
        for (const asset of assetPlan) {
          assets.push({
            assetId: asset.assetId,
            path: asset.path,
            mime: asset.mime,
            sha256: asset.sha256,
            dataUrl: await this.dataUrl(new Blob([asset.bytes], {type: asset.mime}))
          });
        }
        let markdown = "";
        try { markdown = this.serializeMarkdown(assetPaths); } catch (_) { /* operation log and base source remain recoverable */ }
        const targetHash = markdown ? await this.sha256(new TextEncoder().encode(markdown)) : "";
        const bundle = {
          kind: "golajah-edit-bundle",
          schemaVersion: ContentAuthoring.schemaVersion,
          createdAt: new Date().toISOString(),
          error: {code: error.code, message: error.message},
          base: changeSet.base,
          baseSourceText: this.source.text,
          markdown,
          layout: this.layoutPayload(changeSet.layout, targetHash),
          operations: changeSet.operations,
          snapshot: changeSet.snapshot,
          assets
        };
        const source = JSON.stringify(bundle, null, 2) + "\n";
        const stem = this.source.name.split("/").pop().replace(/\.[^.]+$/, "") || "slides";
        this.downloadBlob(new Blob([source], {type: "application/json"}), `${stem}.golajah-edit.json`);
        return {status: "exported", changedFiles: [], needsRebuild: true, bundleName: `${stem}.golajah-edit.json`, error};
      }

      dataUrl(blob) {
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.addEventListener("load", () => resolve(String(reader.result || "")), {once: true});
          reader.addEventListener("error", () => reject(reader.error || new Error("无法读取资产")), {once: true});
          reader.readAsDataURL(blob);
        });
      }

      downloadBlob(blob, name) {
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = name;
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 800);
      }

      normalizeSaveError(error) {
        if (error?.code) return error;
        if (error?.name === "AbortError") return this.saveError("USER_CANCELLED", "用户取消了目录选择", error);
        if (error?.name === "NotAllowedError") return this.saveError("PERMISSION_DENIED", "目录写入授权被拒绝", error);
        if (error?.name === "NotFoundError") return this.saveError("INVALID_PATH", "所选目录中缺少源文件", error);
        return this.saveError("WRITE_FAILED", error?.message || "保存失败", error);
      }

      saveError(code, message, cause = null) {
        const error = new Error(message, cause ? {cause} : undefined);
        error.code = code;
        return error;
      }

      draftKey() {
        return `golajah:content-authoring:v1:${location.pathname}:${this.source.name}`;
      }

      persistDraft() {
        try {
          localStorage.setItem(this.draftKey(), JSON.stringify({
            schemaVersion: ContentAuthoring.schemaVersion,
            baseSourceSha256: this.source.sha256,
            revision: this.revision,
            operations: this.operations
          }));
          this.storageWarning = "";
        } catch (_) {
          this.storageWarning = "浏览器无法暂存内容改动；请立即保存或导出编辑包。";
          this.setStatus(this.storageWarning, "warning");
        }
      }

      restoreDraft() {
        try {
          const saved = JSON.parse(localStorage.getItem(this.draftKey()) || "null");
          if (!saved || !Array.isArray(saved.operations) || !saved.operations.length) return;
          if (!saved.baseSourceSha256 || saved.baseSourceSha256 !== this.source.sha256) {
            this.staleDraft = saved;
            this.dispatch("draft-conflict", {draft: saved, sourceSha256: this.source.sha256});
            this.setStatus("检测到基于旧源码的本地草稿；为避免内容串位，未自动恢复。", "warning");
            return;
          }
          if (saved.operations.some(operation => ["add-media", "replace-media"].includes(operation.op))) {
            this.staleDraft = saved;
            this.dispatch("draft-conflict", {draft: saved, sourceSha256: this.source.sha256, reason: "missing-media-bytes"});
            this.setStatus("本地草稿包含仅存在于上次会话的图片；为避免部分恢复和内容错位，未自动回放。", "warning");
            return;
          }
          saved.operations.forEach(operation => this.applyOperation(operation));
          const latestChapterOperations = new Map();
          const normalizedOperations = [];
          saved.operations.forEach(operation => {
            if (operation.op === "set-chapter") latestChapterOperations.set(operation.slideId, operation);
            else normalizedOperations.push(structuredClone(operation));
          });
          latestChapterOperations.forEach((operation, slideId) => {
            if (this.slideStates.get(slideId)?.chapterChanged) normalizedOperations.push(structuredClone(operation));
          });
          this.operations = normalizedOperations;
          this.dirty = this.operations.length > 0;
          this.revision = this.dirty ? (Number(saved.revision) || this.operations.length) : 0;
          if (this.dirty) {
            this.persistDraft();
            this.setStatus("已恢复与当前源码指纹匹配的本地草稿。", "dirty");
          } else {
            this.clearDraft();
            this.setStatus("本地草稿已与构建时状态一致，无需恢复。", "clean");
          }
        } catch (_) {
          this.storageWarning = "本地内容草稿无法读取，已忽略。";
        }
      }

      applyOperation(operation) {
        const options = {record: false, announce: false, select: false, navigate: false};
        if (operation.op === "add" && operation.item) {
          const state = this.slideStates.get(operation.slideId);
          if (!state || this.items.has(operation.item.id)) return;
          const item = this.registerItem(state, {...operation.item, created: true});
          if (!item) return;
          const node = this.createBlockNode(item);
          this.nodes.set(item.id, node);
          this.insertInLane(state, item.id, operation.beforeItemId || null);
          this.markContentChanged(state);
          this.reconcileSlides([state.id]);
        } else if (operation.op === "update-field") {
          this.updateField(operation.itemId, operation.field, operation.value, options);
        } else if (operation.op === "reorder") {
          this.reorderItem(operation.slideId, operation.itemId, operation.beforeItemId || null, options);
        } else if (operation.op === "move") {
          this.moveItem(operation.itemId, operation.toSlideId, operation.beforeItemId || null, options);
        } else if (operation.op === "set-gallery-display") {
          this.setGalleryDisplay(operation.slideId, operation.display, options);
        } else if (operation.op === "set-chapter") {
          this.setChapterItem(operation.slideId, operation.chapter || "", options);
        }
      }

      clearDraft() {
        try { localStorage.removeItem(this.draftKey()); } catch (_) { /* noop */ }
      }

      refreshPanel() {
        if (!this.panel) return;
        const state = this.slideStates.get(this.currentSlideId());
        const canEdit = state?.kind === "content" && !this.needsRebuild;
        const selectedItem = this.items.get(this.selectedId);
        if (this.modeButton) this.modeButton.disabled = this.needsRebuild;
        this.panel.querySelectorAll('[data-author-action="add-text"],[data-author-action="add-callout"]')
          .forEach(button => button.disabled = !canEdit);
        const upload = this.panel.querySelector('[data-author-action="upload-image"]');
        if (upload) upload.disabled = !canEdit || (this.hasSpecializedItems(state) && !ContentAuthoring.mediaKinds.has(selectedItem?.kind));
        const gallery = this.panel.querySelector("[data-author-gallery]");
        const mediaCount = this.mediaItemIds(state).length;
        gallery.hidden = !canEdit || this.hasSpecializedItems(state) || mediaCount < 2;
        gallery.querySelectorAll("[data-author-gallery-display]").forEach(button => {
          button.setAttribute("aria-pressed", String(button.dataset.authorGalleryDisplay === state?.galleryDisplay));
        });
        this.renderChapterPanel(state, canEdit);
        this.renderOrderList(state);
        this.renderSelection();
        if (this.saveButton) this.saveButton.disabled = !this.dirty || this.needsRebuild;
        if (!this.dirty && !this.storageWarning && !this.staleDraft) this.setStatus("尚无内容改动。", "clean");
      }

      renderChapterPanel(state, canEdit) {
        if (!this.chapterSelect) return;
        const sectionName = this.panel.querySelector("[data-author-section-name]");
        if (sectionName) sectionName.textContent = state?.section || "无 Section";
        const previousValue = state?.chapter || "";
        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = state?.title ? `使用页面标题：${state.title}` : "使用页面标题（默认）";
        const options = [defaultOption];
        this.chapterItemsForSlide(state?.id).forEach(item => {
          if (item.title === state?.title && !state?.chapter) return;
          const option = document.createElement("option");
          option.value = item.title;
          option.textContent = `${item.title} · P.${item.page}`;
          options.push(option);
        });
        this.chapterSelect.replaceChildren(...options);
        this.chapterSelect.value = previousValue;
        this.chapterSelect.disabled = !canEdit || !state?.section;
        const addButton = this.panel.querySelector('[data-author-action="show-new-chapter"]');
        if (addButton) addButton.disabled = !canEdit || !state?.section;
        if ((!canEdit || !state?.section) && this.chapterCreate) this.chapterCreate.hidden = true;
        const help = this.panel.querySelector("[data-author-chapter-help]");
        if (help) help.textContent = state?.section
          ? "选择已有 item，或新增并把当前页归入它；保存并重新构建后页脚同步更新。"
          : "请先在 Markdown 中配置 Section，再设置 Chapter item。";
      }

      renderOrderList(state) {
        if (!this.orderList) return;
        this.orderList.replaceChildren();
        const ids = this.blockItemIds(state);
        ids.forEach((id, index) => {
          const item = this.items.get(id);
          const row = document.createElement("li");
          row.dataset.authorOrderItem = id;
          row.draggable = this.active;
          row.classList.toggle("is-selected", id === this.selectedId);
          const handle = document.createElement("button");
          handle.type = "button";
          handle.className = "content-authoring-drag-handle";
          handle.dataset.authorAction = "select";
          handle.setAttribute("aria-label", `选择并拖动${item.title || item.kind}`);
          handle.textContent = "⋮⋮";
          const label = document.createElement("button");
          label.type = "button";
          label.className = "content-authoring-order-label";
          label.dataset.authorAction = "select";
          label.textContent = item.title || (item.kind === "callout" ? "Callout" : "未命名文本块");
          const controls = document.createElement("span");
          controls.className = "content-authoring-order-controls";
          controls.innerHTML = '<button type="button" data-author-action="order-up" aria-label="上移">↑</button><button type="button" data-author-action="order-down" aria-label="下移">↓</button>';
          controls.firstElementChild.disabled = index === 0;
          controls.lastElementChild.disabled = index === ids.length - 1;
          row.append(handle, label, controls);
          this.orderList.appendChild(row);
        });
        this.orderList.hidden = !ids.length;
      }

      renderSelection() {
        if (!this.selectionPanel) return;
        const item = this.items.get(this.selectedId);
        const visible = Boolean(item && item.slideId === this.currentSlideId());
        this.selectionPanel.hidden = !visible;
        if (!visible) return;
        this.selectionPanel.querySelector("[data-author-selection-kind]").textContent = item.kind === "callout" ? "Callout" : item.kind === "text" ? "文本块" : "图片";
        const title = this.selectionPanel.querySelector('[data-author-input="title"]');
        const body = this.selectionPanel.querySelector('[data-author-input="body"]');
        const textLike = ContentAuthoring.blockKinds.has(item.kind);
        this.selectionPanel.querySelector("[data-author-title-row]").hidden = !textLike;
        this.selectionPanel.querySelector("[data-author-body-row]").hidden = !textLike;
        if (textLike) {
          title.value = item.title;
          body.value = item.body;
        }
        const slides = [...this.slideStates.values()].sort((left, right) => left.index - right.index);
        const current = this.slideStates.get(item.slideId);
        const previous = slides[current.index - 1];
        const next = slides[current.index + 1];
        const canMoveTo = target => Boolean(target && target.kind === "content"
          && !(ContentAuthoring.mediaKinds.has(item.kind) && this.hasSpecializedItems(target)));
        this.selectionPanel.querySelector('[data-author-action="move-prev"]').disabled = !canMoveTo(previous);
        this.selectionPanel.querySelector('[data-author-action="move-next"]').disabled = !canMoveTo(next);
      }

      setStatus(message, state = "") {
        if (!this.statusNode) return;
        this.statusNode.textContent = message;
        this.statusNode.dataset.state = state;
      }

      reportError(error, prefix = "内容编辑失败") {
        this.setStatus(`${prefix}：${error?.message || error}`, "warning");
        this.dispatch("error", {error, prefix});
      }

      dispatch(name, detail, options = {}) {
        return this.stage.dispatchEvent(new CustomEvent(`content-authoring:${name}`, {
          bubbles: true,
          cancelable: options.cancelable === true,
          detail
        }));
      }
    }

    window.ContentAuthoring = ContentAuthoring;
