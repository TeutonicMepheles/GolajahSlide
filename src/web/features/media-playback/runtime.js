    class MediaPlayback {
      constructor() {
        this.videos = [...document.querySelectorAll("[data-slide-video]")];
        this.stage = document.getElementById("deckStage");
        this.bind();
        this.sync();
      }
      bind() {
        this.videos.forEach(video => {
          ["click", "dblclick", "pointerdown", "touchstart", "touchend", "wheel"].forEach(type => {
            video.addEventListener(type, event => event.stopPropagation(), {passive: type !== "wheel"});
          });
        });
        this.observer = new MutationObserver(records => {
          if (records.some(record => (
            record.target.classList?.contains("slide") || record.target.hasAttribute?.("data-media-panel")
          ))) this.sync();
        });
        if (this.stage) this.observer.observe(this.stage, {subtree: true, attributes: true, attributeFilter: ["class"]});
      }
      sync() {
        this.videos.forEach(video => {
          const mediaPanel = video.closest("[data-media-panel]");
          const panelIsActive = !mediaPanel || mediaPanel.classList.contains("active");
          if (!video.closest(".slide.active") || !panelIsActive) {
            if (!video.paused) video.pause();
            return;
          }
          if (video.hasAttribute("data-video-autoplay") && video.paused) {
            const playPromise = video.play();
            if (playPromise?.catch) playPromise.catch(() => {});
          }
        });
      }
    }
