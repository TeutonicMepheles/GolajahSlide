// Read layout coordinates without presentation scaling or reveal transforms.
function measureLayoutRegions(slide, parts) {
  function bounds(node) {
    if (!node || !node.offsetWidth || !node.offsetHeight) return null;
    let x = 0, y = 0, current = node;
    while (current && current !== slide) {
      x += current.offsetLeft;
      y += current.offsetTop;
      current = current.offsetParent;
    }
    if (current !== slide) return null;
    return {x, y, width: node.offsetWidth, height: node.offsetHeight};
  }
  const visual = bounds(parts.visual);
  const copy = bounds(parts.copy);
  let content = bounds(parts.content);
  if (slide.dataset.slideKind !== "content") {
    const children = [visual, copy].filter(Boolean);
    if (!children.length) return null;
    const x = Math.min(...children.map(rect => rect.x));
    const y = Math.min(...children.map(rect => rect.y));
    content = {x, y,
      width: Math.max(...children.map(rect => rect.x + rect.width)) - x,
      height: Math.max(...children.map(rect => rect.y + rect.height)) - y};
  }
  return content ? {content, ...(visual && {visual}), ...(copy && {copy})} : null;
}
