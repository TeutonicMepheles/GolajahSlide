    class StaticDeckExport {
      constructor({slides, deckTitle, mount, sanitizeClone, assetManifest} = {}) {
        this.slides = slides ? [...slides] : [...document.querySelectorAll(".slide")];
        this.deckTitle = String(deckTitle || document.title || "GolajahSlide");
        this.mount = typeof mount === "string" ? document.querySelector(mount) : mount;
        this.sanitizeClone = typeof sanitizeClone === "function" ? sanitizeClone : null;
        this.assetManifest = this.normalizeAssetManifest(assetManifest);
        this.stageSize = {width: 1920, height: 1080};
        this.slideSize = {width: 12192000, height: 6858000};
        this.pdfSize = {width: 960, height: 540};
        this.jpegQuality = 0.94;
        this.rasterByteLimit = 512 * 1024 * 1024;
        this.busy = false;
        this.lastResult = null;
        this.encoder = new TextEncoder();
        this.mountControls();
      }

      normalizeAssetManifest(manifest) {
        const sources = manifest?.sources && typeof manifest.sources === "object" ? manifest.sources : {};
        const assets = manifest?.assets && typeof manifest.assets === "object" ? manifest.assets : {};
        return {sources, assets};
      }

      prepareClone(clone) {
        const mount = clone.querySelector?.("#editorStaticExportMount");
        if (!mount) return;
        mount.setAttribute("aria-busy", "false");
        mount.querySelectorAll("#editorExportPdf,#editorExportPptx").forEach(button => {
          button.disabled = false;
          button.setAttribute("aria-busy", "false");
        });
        const progress = mount.querySelector("#editorStaticExportProgress");
        if (progress) progress.hidden = true;
        const status = mount.querySelector("#editorStaticExportStatus");
        if (status) {
          status.textContent = "尚未导出。";
          status.dataset.state = "idle";
        }
      }

      mountControls() {
        if (!this.mount) return;
        this.mount.innerHTML = `
          <section class="editor-group static-export-panel" aria-labelledby="editorStaticExportTitle">
            <div class="editor-label" id="editorStaticExportTitle">演示文稿导出 <span>默认无动效</span></div>
            <div class="editor-button-row static-export-actions">
              <button type="button" class="editor-button primary" id="editorExportPdf">导出 PDF</button>
              <button type="button" class="editor-button" id="editorExportPptx">导出 PowerPoint</button>
            </div>
            <div class="static-export-progress" id="editorStaticExportProgress" hidden>
              <progress max="1" value="0" aria-label="导出进度"></progress>
              <span>准备导出…</span>
            </div>
            <p class="editor-help" id="editorStaticExportHelp">直接下载 16:9 静态文件；所有内容均显示，Tab Gallery 会逐项展开为连续页面。PDF 文字不可搜索，PPTX 页面不可拆分编辑，链接与动效不保留。</p>
            <p class="static-export-status" id="editorStaticExportStatus" role="status" aria-live="polite">尚未导出。</p>
          </section>`;
        this.pdfButton = this.mount.querySelector("#editorExportPdf");
        this.pptxButton = this.mount.querySelector("#editorExportPptx");
        this.progressRoot = this.mount.querySelector("#editorStaticExportProgress");
        this.progressBar = this.progressRoot.querySelector("progress");
        this.progressLabel = this.progressRoot.querySelector("span");
        this.statusNode = this.mount.querySelector("#editorStaticExportStatus");
        this.pdfButton.addEventListener("click", () => this.exportPdf().catch(() => {}));
        this.pptxButton.addEventListener("click", () => this.exportPptx().catch(() => {}));
      }

      safeBaseName() {
        const normalized = this.deckTitle.normalize("NFKC")
          .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
          .replace(/\s+/g, " ")
          .replace(/[. ]+$/g, "")
          .trim()
          .slice(0, 80);
        return normalized || "GolajahSlide";
      }

      setBusy(busy) {
        this.busy = busy === true;
        [this.pdfButton, this.pptxButton].filter(Boolean).forEach(button => {
          button.disabled = this.busy;
          button.setAttribute("aria-busy", String(this.busy));
        });
        if (this.mount) this.mount.setAttribute("aria-busy", String(this.busy));
      }

      updateProgress(value, max, label) {
        if (!this.progressRoot) return;
        this.progressRoot.hidden = false;
        this.progressBar.max = Math.max(1, max);
        this.progressBar.value = Math.max(0, Math.min(value, max));
        this.progressLabel.textContent = label;
      }

      hideProgress() {
        if (this.progressRoot) this.progressRoot.hidden = true;
      }

      setStatus(message, state = "idle") {
        if (!this.statusNode) return;
        this.statusNode.textContent = message;
        this.statusNode.dataset.state = state;
      }

      emit(name, detail = {}) {
        (this.mount || document).dispatchEvent(new CustomEvent(`static-export:${name}`, {
          bubbles: true,
          detail
        }));
      }

      snapshotPlan() {
        const plan = [];
        this.slides.forEach((slide, slideIndex) => {
          const shells = [...slide.querySelectorAll("[data-media-tabs]")];
          let variants = [[]];
          shells.forEach((shell, shellIndex) => {
            const choices = [...shell.querySelectorAll("[data-media-target]")].map(button => ({
              shellIndex,
              target: String(button.dataset.mediaTarget || ""),
              label: (button.textContent || button.getAttribute("aria-label") || "").trim()
            }));
            if (!choices.length) return;
            variants = variants.flatMap(existing => choices.map(choice => [...existing, choice]));
            if (variants.length > 32) throw new Error(`P${slideIndex + 1} 的 Gallery 组合超过 32 个，无法安全导出`);
          });
          variants.forEach((selections, variantIndex) => {
            const baseTitle = slide.dataset.title || `P${slideIndex + 1}`;
            const suffix = selections.map(selection => selection.label).filter(Boolean).join(" · ");
            plan.push({
              slide,
              slideIndex,
              slideId: slide.dataset.slideId || `P${slideIndex + 1}`,
              variantIndex,
              selections,
              title: suffix ? `${baseTitle} · ${suffix}` : baseTitle
            });
          });
        });
        return plan;
      }

      async exportPdf({download = true} = {}) {
        return this.exportFile("pdf", {download});
      }

      async exportPptx({download = true} = {}) {
        return this.exportFile("pptx", {download});
      }

      async exportFile(format, {download = true} = {}) {
        if (!new Set(["pdf", "pptx"]).has(format)) throw new Error(`不支持的导出格式：${format}`);
        if (this.busy) throw new Error("已有导出任务正在进行");
        this.setBusy(true);
        this.setStatus("正在准备无动效静态导出…", "working");
        const plan = this.snapshotPlan();
        this.emit("start", {format, pages: plan.length, sourceSlides: this.slides.length});
        try {
          const frames = await this.renderFrames(plan);
          this.updateProgress(plan.length, plan.length, format === "pdf" ? "正在封装 PDF…" : "正在封装 PowerPoint…");
          await new Promise(resolve => requestAnimationFrame(() => resolve()));
          const blob = format === "pdf" ? this.buildPdf(frames) : this.buildPptx(frames);
          const filename = `${this.safeBaseName()}.${format}`;
          if (download) this.downloadBlob(blob, filename);
          this.lastResult = {
            format,
            filename,
            pages: frames.length,
            sourceSlides: this.slides.length,
            bytes: blob.size,
            manifest: plan.map(({slideId, slideIndex, variantIndex, selections, title}) => ({
              slideId,
              slideIndex,
              variantIndex,
              selections: selections.map(({target, label}) => ({target, label})),
              title
            }))
          };
          this.setStatus(`已导出 ${format.toUpperCase()} · ${frames.length} 页无动效静态画面`, "success");
          this.emit("complete", {...this.lastResult, blob});
          return {blob, ...this.lastResult};
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          this.setStatus(`导出失败：${message}`, "error");
          this.emit("error", {format, message});
          throw error;
        } finally {
          this.setBusy(false);
          this.hideProgress();
        }
      }

      async renderFrames(plan = this.snapshotPlan()) {
        if (!plan.length) throw new Error("演示文稿没有可导出的页面");
        if (document.fonts?.ready) await document.fonts.ready;
        const frames = [];
        let rasterBytes = 0;
        for (let index = 0; index < plan.length; index += 1) {
          const entry = plan[index];
          this.updateProgress(index, plan.length, `正在生成第 ${index + 1}/${plan.length} 页…`);
          this.emit("progress", {phase: "render", current: index + 1, total: plan.length, slideId: entry.slideId});
          await new Promise(resolve => requestAnimationFrame(() => resolve()));
          const frame = await this.renderFrame(entry);
          rasterBytes += frame.bytes.length;
          if (rasterBytes > this.rasterByteLimit) throw new Error("静态页面数据超过 512 MB，请拆分演示文稿后导出");
          frames.push(frame);
          this.updateProgress(index + 1, plan.length, `已生成 ${index + 1}/${plan.length} 页`);
        }
        return frames;
      }

      async renderFrame(entry) {
        const clone = entry.slide.cloneNode(true);
        if (this.sanitizeClone) this.sanitizeClone(clone);
        clone.classList.add("active", "visible", "static-export-slide");
        clone.classList.remove("diagnostic-layout");
        clone.removeAttribute("inert");
        clone.querySelectorAll(".layout-editor-overlay, .animation-editor-overlay, .presenter-pointer-cue, .visual-widget-tools, .visual-widget-close, .visual-widget-status, .visual-annotation-layer, .global-logo-resize-handle").forEach(node => node.remove());
        clone.querySelectorAll(".is-author-selected, .presenter-focus-active, .is-zoomed, .is-panning, .is-drawing, .is-annotating, .is-space-pan, .is-fullscreen, .is-fallback-fullscreen, .is-disabled").forEach(node => {
          node.classList.remove("is-author-selected", "presenter-focus-active", "is-zoomed", "is-panning", "is-drawing", "is-annotating", "is-space-pan", "is-fullscreen", "is-fallback-fullscreen", "is-disabled");
        });
        clone.querySelectorAll("[contenteditable]").forEach(node => node.removeAttribute("contenteditable"));
        this.applyGallerySelections(clone, entry.selections);
        await this.freezeMedia(entry.slide, clone, entry);
        clone.querySelectorAll("[data-media-panel]:not(.active)").forEach(node => node.remove());
        const stage = document.createElement("main");
        stage.className = "deck-stage static-export-stage";
        stage.setAttribute("aria-hidden", "true");
        stage.appendChild(clone);
        const markup = new XMLSerializer().serializeToString(stage);
        const styles = this.exportStyleText();
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${this.stageSize.width}" height="${this.stageSize.height}" viewBox="0 0 ${this.stageSize.width} ${this.stageSize.height}"><style><![CDATA[${styles}]]></style><foreignObject x="0" y="0" width="${this.stageSize.width}" height="${this.stageSize.height}"><body xmlns="http://www.w3.org/1999/xhtml" class="static-export-document">${markup}</body></foreignObject></svg>`;
        const svgBytes = this.encoder.encode(svg);
        const image = await this.loadImage(`data:image/svg+xml;base64,${this.bytesToBase64(svgBytes)}`, entry.title);
        const canvas = document.createElement("canvas");
        canvas.width = this.stageSize.width;
        canvas.height = this.stageSize.height;
        const context = canvas.getContext("2d", {alpha: false, colorSpace: "srgb"});
        if (!context) throw new Error(`${entry.title}：浏览器无法创建导出画布`);
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        const blob = await this.canvasBlob(canvas, "image/jpeg", this.jpegQuality, entry.title);
        const bytes = new Uint8Array(await blob.arrayBuffer());
        return {bytes, width: canvas.width, height: canvas.height, title: entry.title, slideId: entry.slideId};
      }

      applyGallerySelections(clone, selections) {
        const shells = [...clone.querySelectorAll("[data-media-tabs]")];
        selections.forEach(selection => {
          const shell = shells[selection.shellIndex];
          if (!shell) return;
          shell.querySelectorAll("[data-media-target]").forEach(button => {
            const active = String(button.dataset.mediaTarget || "") === selection.target;
            button.classList.toggle("active", active);
            button.setAttribute("aria-selected", String(active));
          });
          shell.querySelectorAll("[data-media-panel]").forEach(panel => {
            panel.classList.toggle("active", String(panel.dataset.mediaPanel || "") === selection.target);
          });
        });
      }

      async freezeMedia(original, clone, entry) {
        if (clone.querySelector("iframe, object, embed")) throw new Error(`${entry.title}：包含无法离线快照的嵌入内容`);
        const originalImages = [...original.querySelectorAll("img")];
        const clonedImages = [...clone.querySelectorAll("img")];
        for (let index = 0; index < clonedImages.length; index += 1) {
          const sourceNode = originalImages[index];
          const targetNode = clonedImages[index];
          if (!sourceNode || !targetNode) continue;
          const authoredSource = sourceNode.getAttribute("src") || "";
          const reducedMotionPoster = sourceNode.closest("picture")?.querySelector('source[media*="prefers-reduced-motion"]')?.getAttribute("srcset")?.trim().split(/\s+/)[0] || "";
          const source = reducedMotionPoster || sourceNode.currentSrc || authoredSource;
          if (!source) continue;
          targetNode.removeAttribute("srcset");
          if (reducedMotionPoster) {
            targetNode.src = await this.resourceAsDataUrl(reducedMotionPoster, entry.title, reducedMotionPoster);
          } else if (this.isAnimatedRaster(source)) {
            const dataUrl = await this.resourceAsDataUrl(source, entry.title, authoredSource);
            targetNode.src = await this.freezeAnimatedSource(dataUrl, sourceNode, entry.title);
          } else {
            targetNode.src = await this.resourceAsDataUrl(source, entry.title, authoredSource);
          }
        }
        const originalVideos = [...original.querySelectorAll("video")];
        const clonedVideos = [...clone.querySelectorAll("video")];
        for (let index = 0; index < clonedVideos.length; index += 1) {
          const sourceNode = originalVideos[index];
          const targetNode = clonedVideos[index];
          if (!sourceNode || !targetNode) continue;
          targetNode.replaceWith(await this.videoReplacement(sourceNode, entry.title));
        }
        const originalCanvases = [...original.querySelectorAll("canvas")];
        const clonedCanvases = [...clone.querySelectorAll("canvas")];
        for (let index = 0; index < clonedCanvases.length; index += 1) {
          const sourceNode = originalCanvases[index];
          const targetNode = clonedCanvases[index];
          if (!sourceNode || !targetNode) continue;
          const image = document.createElement("img");
          image.className = targetNode.className;
          image.style.cssText = targetNode.style.cssText;
          image.width = sourceNode.width;
          image.height = sourceNode.height;
          try {
            image.src = sourceNode.toDataURL("image/png");
          } catch (_) {
            throw new Error(`${entry.title}：Canvas 含有跨域内容，无法离线导出`);
          }
          targetNode.replaceWith(image);
        }
        await this.inlineSvgImages(original, clone, entry.title);
        await this.inlineStyleUrls(original, clone, entry.title);
      }

      isAnimatedRaster(source) {
        return /^data:image\/(?:gif|webp);/i.test(source) || /\.(?:gif|webp)(?:[?#]|$)/i.test(source);
      }

      async freezeAnimatedSource(source, fallbackImage, label) {
        if (typeof ImageDecoder === "function") {
          try {
            const response = await fetch(source);
            const blob = await response.blob();
            const decoder = new ImageDecoder({data: await blob.arrayBuffer(), type: blob.type});
            const result = await decoder.decode({frameIndex: 0});
            const frame = result.image;
            const canvas = document.createElement("canvas");
            canvas.width = frame.displayWidth;
            canvas.height = frame.displayHeight;
            canvas.getContext("2d").drawImage(frame, 0, 0);
            frame.close();
            decoder.close();
            return canvas.toDataURL("image/png");
          } catch (_) { /* older decoders fall through to the loaded-image snapshot */ }
        }
        const image = await this.loadImage(source, label);
        const width = image.naturalWidth || fallbackImage.naturalWidth;
        const height = image.naturalHeight || fallbackImage.naturalHeight;
        if (!width || !height) throw new Error(`${label}：动画图片尚未加载完成`);
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d");
        try {
          context.drawImage(image, 0, 0);
          return canvas.toDataURL("image/png");
        } catch (_) {
          throw new Error(`${label}：动画图片含有跨域内容，无法冻结`);
        }
      }

      async videoReplacement(video, label) {
        const image = document.createElement("img");
        image.className = `${video.className || ""} static-export-video-frame`.trim();
        image.style.cssText = video.style.cssText;
        image.alt = video.getAttribute("aria-label") || "视频静态画面";
        if (video.poster) {
          image.src = await this.resourceAsDataUrl(video.poster, label, video.getAttribute("poster") || "");
          return image;
        }
        if (video.readyState >= 2 && video.videoWidth && video.videoHeight) {
          const canvas = document.createElement("canvas");
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          const context = canvas.getContext("2d");
          try {
            context.drawImage(video, 0, 0);
            image.src = canvas.toDataURL("image/png");
            return image;
          } catch (_) { /* fall through to the deterministic placeholder */ }
        }
        const fallback = document.createElement("div");
        fallback.className = "static-export-video-fallback";
        fallback.setAttribute("role", "img");
        fallback.setAttribute("aria-label", image.alt);
        fallback.textContent = "视频 · 静态导出";
        return fallback;
      }

      async inlineSvgImages(original, clone, label) {
        const originals = [...original.querySelectorAll("image")];
        const clones = [...clone.querySelectorAll("image")];
        for (let index = 0; index < clones.length; index += 1) {
          const sourceNode = originals[index];
          const targetNode = clones[index];
          if (!sourceNode || !targetNode) continue;
          const source = sourceNode.getAttribute("href") || sourceNode.getAttribute("xlink:href") || "";
          if (!source || source.startsWith("#")) continue;
          const dataUrl = await this.resourceAsDataUrl(source, label, source);
          targetNode.setAttribute("href", dataUrl);
          targetNode.removeAttribute("xlink:href");
        }
      }

      async inlineStyleUrls(original, clone, label) {
        const originals = [original, ...original.querySelectorAll("*")];
        const clones = [clone, ...clone.querySelectorAll("*")];
        for (let index = 0; index < clones.length; index += 1) {
          const sourceNode = originals[index];
          const targetNode = clones[index];
          if (!sourceNode || !targetNode?.style) continue;
          for (const property of sourceNode.style) {
            const value = sourceNode.style.getPropertyValue(property);
            const matches = [...value.matchAll(/url\((['"]?)(.*?)\1\)/g)];
            if (!matches.length) continue;
            let updated = value;
            for (const match of matches) {
              const source = match[2];
              if (!source || source.startsWith("data:") || source.startsWith("#")) continue;
              const dataUrl = await this.resourceAsDataUrl(source, label, source);
              updated = updated.replace(match[0], `url("${dataUrl}")`);
            }
            targetNode.style.setProperty(property, updated, sourceNode.style.getPropertyPriority(property));
          }
        }
      }

      manifestDataUrl(...references) {
        for (const reference of references) {
          if (!reference) continue;
          const candidates = [reference, reference.replace(/^\.\//, "")];
          for (const candidate of candidates) {
            const digest = this.assetManifest.sources[candidate];
            const dataUrl = digest && this.assetManifest.assets[digest];
            if (typeof dataUrl === "string" && dataUrl.startsWith("data:image/")) return dataUrl;
          }
        }
        return "";
      }

      async resourceAsDataUrl(source, label, authoredSource = "") {
        if (!source || source.startsWith("data:")) return source;
        const embedded = this.manifestDataUrl(authoredSource, source);
        if (embedded) return embedded;
        if (!source.startsWith("blob:")) {
          throw new Error(`${label}：资源不是内嵌文件，无法离线导出（${source.slice(0, 80)}）`);
        }
        let response;
        try { response = await fetch(source); } catch (_) { throw new Error(`${label}：无法读取本地临时图片`); }
        if (!response.ok) throw new Error(`${label}：无法读取本地临时图片`);
        return this.blobAsDataUrl(await response.blob());
      }

      blobAsDataUrl(blob) {
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.addEventListener("load", () => resolve(String(reader.result || "")), {once: true});
          reader.addEventListener("error", () => reject(new Error("无法编码导出图片")), {once: true});
          reader.readAsDataURL(blob);
        });
      }

      exportStyleText() {
        const source = [...document.querySelectorAll("style")].map(node => node.textContent || "").join("\n");
        const staticStyles = `
          * { animation: none !important; transition: none !important; caret-color: transparent !important; }
          html, body.static-export-document { width: 1920px !important; height: 1080px !important; margin: 0 !important; overflow: hidden !important; background: #fff !important; }
          body.static-export-document { position: relative !important; }
          .static-export-stage { position: relative !important; inset: auto !important; left: 0 !important; top: 0 !important; width: 1920px !important; height: 1080px !important; transform: none !important; overflow: hidden !important; }
          .static-export-slide { position: absolute !important; inset: 0 !important; display: block !important; visibility: visible !important; opacity: 1 !important; pointer-events: none !important; z-index: 1 !important; }
          .static-export-slide .reveal { opacity: 1 !important; transform: none !important; transition: none !important; }
          .static-export-slide::after { display: none !important; }
          .static-export-slide :is(.layout-editor-overlay, .animation-editor-overlay, .visual-widget-tools, .visual-widget-close, .visual-widget-status, .visual-annotation-layer, .global-logo-resize-handle) { display: none !important; }
          .static-export-slide [data-visual-content] { transform: none !important; }
          .static-export-video-frame { display: block !important; width: 100% !important; height: 100% !important; object-fit: contain; }
          .static-export-video-fallback { display: grid; width: 100%; height: 100%; place-items: center; color: rgba(255,255,255,.78); background: #07090d; font: 700 32px/1.2 sans-serif; }
        `;
        return `${source}\n${staticStyles}`.replaceAll("]]>", "]]]]><![CDATA[>");
      }

      loadImage(source, label) {
        return new Promise((resolve, reject) => {
          const image = new Image();
          image.decoding = "sync";
          image.addEventListener("load", () => resolve(image), {once: true});
          image.addEventListener("error", () => reject(new Error(`${label}：浏览器无法渲染静态页面快照`)), {once: true});
          image.src = source;
        });
      }

      canvasBlob(canvas, type, quality, label) {
        return new Promise((resolve, reject) => {
          try {
            canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error(`${label}：无法编码静态页面`)), type, quality);
          } catch (_) {
            reject(new Error(`${label}：页面包含无法离线导出的跨域内容`));
          }
        });
      }

      buildPdf(frames) {
        const objects = [null, null];
        const addObject = body => {
          objects.push(body);
          return objects.length;
        };
        const pageIds = [];
        frames.forEach(frame => {
          const imageId = addObject(this.concatBytes([
            this.encoder.encode(`<< /Type /XObject /Subtype /Image /Width ${frame.width} /Height ${frame.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${frame.bytes.length} >>\nstream\n`),
            frame.bytes,
            this.encoder.encode("\nendstream")
          ]));
          const commands = this.encoder.encode(`q\n${this.pdfSize.width} 0 0 ${this.pdfSize.height} 0 0 cm\n/Im1 Do\nQ\n`);
          const contentId = addObject(this.concatBytes([
            this.encoder.encode(`<< /Length ${commands.length} >>\nstream\n`),
            commands,
            this.encoder.encode("endstream")
          ]));
          const pageId = addObject(this.encoder.encode(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${this.pdfSize.width} ${this.pdfSize.height}] /Resources << /XObject << /Im1 ${imageId} 0 R >> >> /Contents ${contentId} 0 R >>`));
          pageIds.push(pageId);
        });
        objects[0] = this.encoder.encode("<< /Type /Catalog /Pages 2 0 R >>");
        objects[1] = this.encoder.encode(`<< /Type /Pages /Count ${pageIds.length} /Kids [${pageIds.map(id => `${id} 0 R`).join(" ")}] >>`);
        const chunks = [new Uint8Array([37, 80, 68, 70, 45, 49, 46, 52, 10, 37, 255, 255, 255, 255, 10])];
        const offsets = [0];
        let position = chunks[0].length;
        objects.forEach((body, index) => {
          offsets.push(position);
          const objectBytes = this.concatBytes([
            this.encoder.encode(`${index + 1} 0 obj\n`),
            body,
            this.encoder.encode("\nendobj\n")
          ]);
          chunks.push(objectBytes);
          position += objectBytes.length;
        });
        const xrefOffset = position;
        const xref = [
          `xref\n0 ${objects.length + 1}\n`,
          "0000000000 65535 f \n",
          ...offsets.slice(1).map(offset => `${String(offset).padStart(10, "0")} 00000 n \n`),
          `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`
        ].join("");
        chunks.push(this.encoder.encode(xref));
        return new Blob([this.concatBytes(chunks)], {type: "application/pdf"});
      }

      buildPptx(frames) {
        const entries = [];
        const xml = (name, value) => entries.push({name, bytes: this.encoder.encode(value)});
        const binary = (name, bytes) => entries.push({name, bytes});
        const overrides = frames.map((_, index) => `<Override PartName="/ppt/slides/slide${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`).join("");
        xml("[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="jpeg" ContentType="image/jpeg"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/><Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/><Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/><Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/><Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/><Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>${overrides}</Types>`);
        xml("_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>`);
        const timestamp = new Date().toISOString();
        xml("docProps/core.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>${this.escapeXml(this.deckTitle)}</dc:title><dc:creator>GolajahSlide</dc:creator><cp:lastModifiedBy>GolajahSlide</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">${timestamp}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">${timestamp}</dcterms:modified></cp:coreProperties>`);
        xml("docProps/app.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>GolajahSlide</Application><PresentationFormat>On-screen Show (16:9)</PresentationFormat><Slides>${frames.length}</Slides><Notes>0</Notes><HiddenSlides>0</HiddenSlides><MMClips>0</MMClips><ScaleCrop>false</ScaleCrop><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>1.0</AppVersion></Properties>`);
        const slideIds = frames.map((_, index) => `<p:sldId id="${256 + index}" r:id="rId${index + 2}"/>`).join("");
        xml("ppt/presentation.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>${slideIds}</p:sldIdLst><p:sldSz cx="${this.slideSize.width}" cy="${this.slideSize.height}" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/><p:defaultTextStyle/></p:presentation>`);
        const extraBase = frames.length + 2;
        const slideRelationships = frames.map((_, index) => `<Relationship Id="rId${index + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide${index + 1}.xml"/>`).join("");
        xml("ppt/_rels/presentation.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>${slideRelationships}<Relationship Id="rId${extraBase}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/><Relationship Id="rId${extraBase + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/><Relationship Id="rId${extraBase + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/></Relationships>`);
        xml("ppt/presProps.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>`);
        xml("ppt/viewProps.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" lastView="sldView"><p:normalViewPr/><p:slideViewPr><p:cSldViewPr><p:cViewPr varScale="1"><p:scale><a:sx n="100" d="100"/><a:sy n="100" d="100"/></p:scale><p:origin x="0" y="0"/></p:cViewPr><p:guideLst/></p:cSldViewPr></p:slideViewPr><p:notesTextViewPr><p:cViewPr><p:scale><a:sx n="100" d="100"/><a:sy n="100" d="100"/></p:scale><p:origin x="0" y="0"/></p:cViewPr></p:notesTextViewPr><p:gridSpacing cx="78028800" cy="78028800"/></p:viewPr>`);
        xml("ppt/tableStyles.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>`);
        xml("ppt/slideMasters/slideMaster1.xml", this.slideMasterXml());
        xml("ppt/slideMasters/_rels/slideMaster1.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>`);
        xml("ppt/slideLayouts/slideLayout1.xml", this.slideLayoutXml());
        xml("ppt/slideLayouts/_rels/slideLayout1.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>`);
        xml("ppt/theme/theme1.xml", this.themeXml());
        frames.forEach((frame, index) => {
          const number = index + 1;
          xml(`ppt/slides/slide${number}.xml`, this.slideXml(frame, number));
          xml(`ppt/slides/_rels/slide${number}.xml.rels`, `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image${number}.jpeg"/></Relationships>`);
          binary(`ppt/media/image${number}.jpeg`, frame.bytes);
        });
        return new Blob([this.buildZip(entries)], {type: "application/vnd.openxmlformats-officedocument.presentationml.presentation"});
      }

      slideMasterXml() {
        return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="GolajahSlide"><p:spTree>${this.groupShapeXml()}</p:spTree></p:cSld><p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>`;
      }

      slideLayoutXml() {
        return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree>${this.groupShapeXml()}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>`;
      }

      groupShapeXml() {
        return `<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>`;
      }

      slideXml(frame, number) {
        const title = this.escapeXml(frame.title || `Slide ${number}`);
        return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="${title}"><p:spTree>${this.groupShapeXml()}<p:pic><p:nvPicPr><p:cNvPr id="2" name="Slide ${number}" descr="${title}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${this.slideSize.width}" cy="${this.slideSize.height}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:ln><a:noFill/></a:ln></p:spPr></p:pic></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>`;
      }

      themeXml() {
        return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="GolajahSlide"><a:themeElements><a:clrScheme name="GolajahSlide"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="111111"/></a:dk2><a:lt2><a:srgbClr val="F2F0FF"/></a:lt2><a:accent1><a:srgbClr val="6F60E5"/></a:accent1><a:accent2><a:srgbClr val="4C3BC6"/></a:accent2><a:accent3><a:srgbClr val="59A14F"/></a:accent3><a:accent4><a:srgbClr val="F28E2B"/></a:accent4><a:accent5><a:srgbClr val="E15759"/></a:accent5><a:accent6><a:srgbClr val="76B7B2"/></a:accent6><a:hlink><a:srgbClr val="4C3BC6"/></a:hlink><a:folHlink><a:srgbClr val="6F60E5"/></a:folHlink></a:clrScheme><a:fontScheme name="GolajahSlide"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme><a:fmtScheme name="GolajahSlide"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="50000"/><a:satMod val="300000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="100000"/><a:satMod val="200000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="16200000" scaled="1"/></a:gradFill><a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:shade val="51000"/><a:satMod val="130000"/></a:schemeClr></a:gs><a:gs pos="80000"><a:schemeClr val="phClr"><a:shade val="93000"/><a:satMod val="130000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="94000"/><a:satMod val="135000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="16200000" scaled="0"/></a:gradFill></a:fillStyleLst><a:lnStyleLst><a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln><a:ln w="12700" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln><a:ln w="19050" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/><a:satMod val="170000"/></a:schemeClr></a:solidFill><a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="93000"/><a:satMod val="150000"/><a:shade val="98000"/><a:lumMod val="102000"/></a:schemeClr></a:gs><a:gs pos="50000"><a:schemeClr val="phClr"><a:tint val="98000"/><a:satMod val="130000"/><a:shade val="90000"/><a:lumMod val="103000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="63000"/><a:satMod val="120000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="16200000" scaled="1"/></a:gradFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>`;
      }

      buildZip(entries) {
        if (entries.length >= 65535) throw new Error("PowerPoint 包含过多文件，超过 Zip32 上限");
        const records = entries.map(entry => {
          const name = this.encoder.encode(entry.name);
          const bytes = entry.bytes instanceof Uint8Array ? entry.bytes : new Uint8Array(entry.bytes);
          return {name, bytes, crc: this.crc32(bytes), offset: 0};
        });
        const localSize = records.reduce((sum, record) => sum + 30 + record.name.length + record.bytes.length, 0);
        const centralSize = records.reduce((sum, record) => sum + 46 + record.name.length, 0);
        if (localSize + centralSize + 22 >= 0xffffffff) throw new Error("PowerPoint 文件超过 4 GB Zip32 上限");
        const output = new Uint8Array(localSize + centralSize + 22);
        const view = new DataView(output.buffer);
        let offset = 0;
        records.forEach(record => {
          record.offset = offset;
          view.setUint32(offset, 0x04034b50, true);
          view.setUint16(offset + 4, 20, true);
          view.setUint16(offset + 6, 0x0800, true);
          view.setUint16(offset + 8, 0, true);
          view.setUint16(offset + 10, 0, true);
          view.setUint16(offset + 12, 0x21, true);
          view.setUint32(offset + 14, record.crc, true);
          view.setUint32(offset + 18, record.bytes.length, true);
          view.setUint32(offset + 22, record.bytes.length, true);
          view.setUint16(offset + 26, record.name.length, true);
          view.setUint16(offset + 28, 0, true);
          output.set(record.name, offset + 30);
          output.set(record.bytes, offset + 30 + record.name.length);
          offset += 30 + record.name.length + record.bytes.length;
        });
        const centralOffset = offset;
        records.forEach(record => {
          view.setUint32(offset, 0x02014b50, true);
          view.setUint16(offset + 4, 20, true);
          view.setUint16(offset + 6, 20, true);
          view.setUint16(offset + 8, 0x0800, true);
          view.setUint16(offset + 10, 0, true);
          view.setUint16(offset + 12, 0, true);
          view.setUint16(offset + 14, 0x21, true);
          view.setUint32(offset + 16, record.crc, true);
          view.setUint32(offset + 20, record.bytes.length, true);
          view.setUint32(offset + 24, record.bytes.length, true);
          view.setUint16(offset + 28, record.name.length, true);
          view.setUint16(offset + 30, 0, true);
          view.setUint16(offset + 32, 0, true);
          view.setUint16(offset + 34, 0, true);
          view.setUint16(offset + 36, 0, true);
          view.setUint32(offset + 38, 0, true);
          view.setUint32(offset + 42, record.offset, true);
          output.set(record.name, offset + 46);
          offset += 46 + record.name.length;
        });
        view.setUint32(offset, 0x06054b50, true);
        view.setUint16(offset + 4, 0, true);
        view.setUint16(offset + 6, 0, true);
        view.setUint16(offset + 8, records.length, true);
        view.setUint16(offset + 10, records.length, true);
        view.setUint32(offset + 12, centralSize, true);
        view.setUint32(offset + 16, centralOffset, true);
        view.setUint16(offset + 20, 0, true);
        return output;
      }

      crc32(bytes) {
        if (!StaticDeckExport.crcTable) {
          StaticDeckExport.crcTable = Uint32Array.from({length: 256}, (_, index) => {
            let value = index;
            for (let bit = 0; bit < 8; bit += 1) value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : (value >>> 1);
            return value >>> 0;
          });
        }
        let crc = 0xffffffff;
        for (const byte of bytes) crc = StaticDeckExport.crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
        return (crc ^ 0xffffffff) >>> 0;
      }

      escapeXml(value) {
        return String(value).replace(/[&<>"']/g, character => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"})[character]);
      }

      concatBytes(chunks) {
        const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
        const output = new Uint8Array(length);
        let offset = 0;
        chunks.forEach(chunk => {
          output.set(chunk, offset);
          offset += chunk.length;
        });
        return output;
      }

      bytesToBase64(bytes) {
        let binary = "";
        for (let offset = 0; offset < bytes.length; offset += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(offset, Math.min(bytes.length, offset + 0x8000)));
        }
        return btoa(binary);
      }

      downloadBlob(blob, filename) {
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(link.href), 1500);
      }
    }
