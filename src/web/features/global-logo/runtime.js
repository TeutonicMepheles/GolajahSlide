    class GlobalLogo {
      constructor(config = {}) {
        this.maxFileSize = 2 * 1024 * 1024;
        this.allowedTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
        this.state = this.normalize(config);
        this.nodes = [];
        this.onResizeCommit = null;
      }
      normalize(config) {
        const enabled = config?.enabled === true;
        const src = typeof config?.src === "string" &&
          /^data:image\/(?:png|jpeg|webp);base64,[a-z0-9+/=]+$/i.test(config.src) ? config.src : "";
        const widthValue = Number(config?.width);
        const heightValue = Number(config?.height);
        const width = Number.isFinite(widthValue) ? Math.max(80, Math.min(420, Math.round(widthValue))) : 190;
        const height = Number.isFinite(heightValue) ? Math.max(36, Math.min(180, Math.round(heightValue))) : 72;
        return {enabled, src, width, height};
      }
      attach(slides, onResizeCommit = null) {
        this.onResizeCommit = typeof onResizeCommit === "function" ? onResizeCommit : null;
        this.nodes = [...slides].map(slide => this.ensureNode(slide));
        this.apply();
      }
      ensureNode(slide) {
        let node = slide.querySelector(":scope > [data-global-logo]");
        if (node) {
          this.bindResize(node.querySelector(".global-logo-resize-handle"));
          return node;
        }
        node = document.createElement("div");
        node.className = "global-logo";
        node.dataset.globalLogo = "";
        node.setAttribute("role", "img");
        node.setAttribute("aria-label", "演示文稿 Logo 占位符");
        node.innerHTML = '<img alt="演示文稿 Logo" draggable="false" hidden><span class="global-logo-placeholder" aria-hidden="true">LOGO</span><button type="button" class="global-logo-resize-handle" aria-label="拖动调整全局 Logo 尺寸"></button>';
        this.bindResize(node.querySelector(".global-logo-resize-handle"));
        slide.appendChild(node);
        return node;
      }
      bindResize(handle) {
        if (!handle || handle.dataset.resizeBound === "true") return;
        handle.dataset.resizeBound = "true";
        handle.addEventListener("pointerdown", event => {
          if (!document.body.classList.contains("editor-open")) return;
          event.preventDefault();
          event.stopPropagation();
          handle.setPointerCapture(event.pointerId);
          const start = {x: event.clientX, y: event.clientY, width: this.state.width, height: this.state.height};
          const move = moveEvent => {
            const scale = Number(document.getElementById("deckStage")?.dataset.scale) || 1;
            this.setSize(start.width - (moveEvent.clientX - start.x) / scale, start.height + (moveEvent.clientY - start.y) / scale);
          };
          const end = () => {
            handle.removeEventListener("pointermove", move);
            handle.removeEventListener("pointerup", end);
            handle.removeEventListener("pointercancel", end);
            this.onResizeCommit?.(this.config());
          };
          handle.addEventListener("pointermove", move);
          handle.addEventListener("pointerup", end);
          handle.addEventListener("pointercancel", end);
        });
      }
      apply() {
        this.nodes.forEach(node => {
          const slide = node.closest(".slide");
          const image = node.querySelector("img");
          const hiddenOnSlide = slide?.dataset.globalLogoVisibility === "hidden";
          const visible = this.state.enabled && !hiddenOnSlide;
          node.hidden = !visible;
          node.classList.toggle("has-image", Boolean(this.state.src));
          node.setAttribute("aria-label", this.state.src ? "演示文稿 Logo" : "演示文稿 Logo 占位符");
          node.style.setProperty("--global-logo-width", `${this.state.width}px`);
          node.style.setProperty("--global-logo-height", `${this.state.height}px`);
          slide?.classList.toggle("global-logo-enabled", visible);
          if (this.state.src) {
            image.src = this.state.src;
            image.hidden = false;
          } else {
            image.removeAttribute("src");
            image.hidden = true;
          }
        });
      }
      setEnabled(enabled) {
        this.state.enabled = enabled === true;
        this.apply();
      }
      setConfig(config) {
        this.state = this.normalize(config);
        this.apply();
        return this.config();
      }
      setSource(src) {
        this.state.src = this.normalize({enabled: true, src}).src;
        this.state.enabled = true;
        this.apply();
        return Boolean(this.state.src);
      }
      clearSource() {
        this.state.src = "";
        this.apply();
      }
      setSize(width, height) {
        this.state.width = Math.max(80, Math.min(420, Math.round(Number(width) || 190)));
        this.state.height = Math.max(36, Math.min(180, Math.round(Number(height) || 72)));
        this.apply();
      }
      resetSize() { this.setSize(190, 72); }
      config() { return {...this.state}; }
      async sourceFromFile(file) {
        if (!file) throw new Error("未选择图片");
        if (!this.allowedTypes.has(file.type)) throw new Error("仅支持 PNG、JPEG 或 WebP");
        if (file.size > this.maxFileSize) throw new Error("Logo 文件不能超过 2 MB");
        const source = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.addEventListener("load", () => resolve(String(reader.result || "")), {once: true});
          reader.addEventListener("error", () => reject(new Error("无法读取 Logo 文件")), {once: true});
          reader.readAsDataURL(file);
        });
        if (!this.normalize({enabled: true, src: source}).src) throw new Error("Logo 图片编码无效");
        return source;
      }
    }
