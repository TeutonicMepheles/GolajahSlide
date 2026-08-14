    /* ===========================================
       FOOTER CHAPTER NAVIGATION
       =========================================== */
    class FooterChapterNavigation {
      constructor(presentation) {
        this.presentation = presentation;
        this.items = [...document.querySelectorAll("[data-section-nav-item]")];
        this.openItem = null;
        this.items.forEach(item => this.bindItem(item));
        document.addEventListener("pointerdown", event => {
          if (!event.target.closest?.("[data-section-nav-item]")) this.closeAll();
        }, {passive:true});
        this.slideObserver = new MutationObserver(mutations => {
          if (mutations.some(mutation => mutation.attributeName === "class")) this.closeAll();
        });
        this.presentation.slides.forEach(slide => {
          this.slideObserver.observe(slide, {attributes:true, attributeFilter:["class"]});
        });
      }
      menuFor(item) { return item.querySelector(".section-footer-menu"); }
      buttonsFor(item) { return [...item.querySelectorAll(".section-footer-chapter")]; }
      setOpen(item, open) {
        if (!item || !this.menuFor(item)) return;
        if (open && this.openItem && this.openItem !== item) this.setOpen(this.openItem, false);
        const trigger = item.querySelector("[data-section-nav-trigger]");
        const menu = this.menuFor(item);
        item.classList.toggle("is-open", open);
        trigger.setAttribute("aria-expanded", String(open));
        menu.setAttribute("aria-hidden", String(!open));
        menu.toggleAttribute("inert", !open);
        this.openItem = open ? item : (this.openItem === item ? null : this.openItem);
      }
      closeAll() {
        if (this.openItem) this.setOpen(this.openItem, false);
      }
      focusChapter(item, index) {
        const buttons = this.buttonsFor(item);
        if (!buttons.length) return;
        buttons[(index + buttons.length) % buttons.length].focus();
      }
      bindItem(item) {
        const trigger = item.querySelector("[data-section-nav-trigger]");
        const menu = this.menuFor(item);
        if (!trigger || !menu) return;
        item.addEventListener("pointerenter", () => this.setOpen(item, true));
        item.addEventListener("pointerleave", () => {
          if (!item.contains(document.activeElement)) this.setOpen(item, false);
        });
        item.addEventListener("focusin", () => this.setOpen(item, true));
        item.addEventListener("focusout", () => queueMicrotask(() => {
          if (!item.contains(document.activeElement) && !item.matches(":hover")) this.setOpen(item, false);
        }));
        trigger.addEventListener("click", () => this.setOpen(item, true));
        trigger.addEventListener("keydown", event => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            this.setOpen(item, true);
            this.focusChapter(item, event.key === "ArrowDown" ? 0 : -1);
          } else if (event.key === "Escape") {
            event.preventDefault();
            this.setOpen(item, false);
          }
        });
        menu.addEventListener("keydown", event => {
          const buttons = this.buttonsFor(item);
          const index = buttons.indexOf(document.activeElement);
          if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            const next = event.key === "Home" ? 0 : event.key === "End" ? -1 : index + (event.key === "ArrowDown" ? 1 : -1);
            this.focusChapter(item, next);
          } else if (event.key === "Escape") {
            event.preventDefault();
            trigger.focus();
            this.setOpen(item, false);
          }
        });
        menu.addEventListener("click", event => {
          const button = event.target.closest?.("[data-slide-target]");
          if (!button) return;
          const target = Number.parseInt(button.dataset.slideTarget, 10);
          if (!Number.isFinite(target)) return;
          this.presentation.show(target);
          this.closeAll();
          button.blur();
        });
      }
    }
