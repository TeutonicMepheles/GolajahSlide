import {
  exportToSvg,
  getCommonBounds,
  getNonDeletedElements,
  restore,
} from "@excalidraw/excalidraw";

globalThis.renderExcalidrawScene = async (scene, options = {}) => {
  const restored = restore(scene, null, null);
  const elements = getNonDeletedElements(restored.elements);
  if (!elements.length) {
    throw new Error("Excalidraw scene does not contain visible elements");
  }

  const textElements = elements.filter(
    (element) => element.type === "text" && String(element.text || "").trim(),
  );
  const minimumFontSize = textElements.length
    ? Math.min(...textElements.map((element) => Number(element.fontSize) || 0).filter(Boolean))
    : null;
  const [minX, minY, maxX, maxY] = getCommonBounds(elements);
  const exportPadding = Number(options.exportPadding ?? 32);
  const svg = await exportToSvg({
    elements,
    appState: {
      ...restored.appState,
      exportBackground: false,
      exportEmbedScene: false,
      exportWithDarkMode: false,
      viewBackgroundColor: options.background || "#F8F6F0",
    },
    files: restored.files || {},
    exportPadding,
    skipInliningFonts: true,
  });

  return {
    svg: new XMLSerializer().serializeToString(svg),
    metrics: {
      sourceWidth: Math.max(0, maxX - minX),
      sourceHeight: Math.max(0, maxY - minY),
      minimumFontSize,
      exportPadding,
      elementCount: elements.length,
    },
  };
};

globalThis.excalidrawExporterReady = true;
