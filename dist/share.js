const FORMATS = {
  landscape: { label: 'Landscape', width: 1200, height: 630 },
  square: { label: 'Square', width: 1080, height: 1080 },
  story: { label: 'Story', width: 1080, height: 1920 },
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function button(className, text, action) {
  const node = element('button', className, text);
  node.addEventListener('click', action);
  return node;
}

function fitText(context, text, maxWidth, size) {
  while (size > 14) {
    context.font = `500 ${size}px "Avenir Next", "Segoe UI", sans-serif`;
    if (context.measureText(text).width <= maxWidth) return;
    size -= 1;
  }
}

function drawPoster(source, format, context) {
  const { width, height } = FORMATS[format];
  const canvas = document.createElement('canvas');
  canvas.width = width; canvas.height = height;
  const drawing = canvas.getContext('2d');
  const footer = format === 'story' ? 152 : 94;
  const imageHeight = height - footer;
  const scale = Math.max(width / source.width, imageHeight / source.height);
  const drawnWidth = source.width * scale, drawnHeight = source.height * scale;
  drawing.fillStyle = '#19352f'; drawing.fillRect(0, 0, width, height);
  drawing.imageSmoothingEnabled = false;
  drawing.drawImage(source, (width - drawnWidth) / 2, (imageHeight - drawnHeight) / 2, drawnWidth, drawnHeight);
  drawing.fillStyle = '#f2f2e8'; drawing.fillRect(0, imageHeight, width, footer);
  const middle = imageHeight + footer / 2;
  drawing.fillStyle = '#2d473e'; drawing.textBaseline = 'middle';
  drawing.font = '800 51px "Helvetica Neue", Helvetica, sans-serif';
  drawing.fillText('010', 29, middle + 2);
  drawing.fillStyle = '#a5b2a1'; drawing.fillRect(132, middle - 22, 1, 44);
  const label = context.locationLabel === 'Rotterdam' ? 'Rotterdam in miniature' : context.locationLabel;
  drawing.fillStyle = '#2d473e';
  fitText(drawing, label, width - 480, 24);
  drawing.fillText(label, 157, middle - 11);
  drawing.fillStyle = '#68786b'; drawing.font = '400 13px "Avenir Next", "Segoe UI", sans-serif';
  drawing.fillText('FROM THE CITY TO THE SEA', 158, middle + 16);
  drawing.textAlign = 'right';
  drawing.fillStyle = '#2d473e'; drawing.font = '500 17px "Avenir Next", "Segoe UI", sans-serif';
  drawing.fillText(context.domain, width - 30, middle - 11);
  drawing.fillStyle = '#68786b'; drawing.font = '400 14px "Avenir Next", "Segoe UI", sans-serif';
  drawing.fillText('by @jjpcodes', width - 30, middle + 16);
  drawing.textAlign = 'left';
  drawing.font = '400 10px "Avenir Next", "Segoe UI", sans-serif';
  drawing.fillText('Map data: Gemeente Rotterdam · Kadaster / PDOK (CC BY 4.0)', 29, height - 10);
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('The browser could not create the image.')), 'image/png'));
}

async function captureScene(scene) {
  scene.render();
  await new Promise(resolve => requestAnimationFrame(resolve));
  scene.render();
  const source = scene.getCanvas();
  const copy = document.createElement('canvas');
  copy.width = source.width; copy.height = source.height;
  copy.getContext('2d').drawImage(source, 0, 0);
  return copy;
}

function downloadImage(blob, filename) {
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export async function openShareDialog(context) {
  document.getElementById('share-dialog')?.remove();
  const dialog = element('dialog', 'share-dialog'); dialog.id = 'share-dialog';
  dialog.setAttribute('aria-labelledby', 'share-title');
  const heading = element('div', 'dialog-heading');
  heading.append(element('span', 'eyebrow', '010 / Share'));
  const close = button('close-button', '×', () => dialog.close()); close.setAttribute('aria-label', 'Close share preview'); heading.append(close);
  const title = element('h2', '', 'Share this view'); title.id = 'share-title';
  const intro = element('p', 'share-intro', 'Copy or download an image with a link to this view.');
  const formatControls = element('div', 'share-formats'); formatControls.setAttribute('role', 'group'); formatControls.setAttribute('aria-label', 'Image shape');
  const previewWrap = element('div', 'share-preview-wrap loading');
  const preview = element('img', 'share-preview'); preview.alt = `Rotterdam miniature map around ${context.locationLabel}, with 010 branding and @jjpcodes credit.`; previewWrap.append(preview);
  const actions = element('div', 'share-actions');
  const caption = `Rotterdam in miniature${context.locationLabel !== 'Rotterdam' ? ` · ${context.locationLabel}` : ''}.\nMade by @jjpcodes\n${context.link}`;
  const captionField = element('textarea', 'share-copy'); captionField.readOnly = true; captionField.value = caption; captionField.setAttribute('aria-label', 'Caption and link to copy');
  const status = element('p', 'share-status', 'Preparing the image…'); status.setAttribute('role', 'status');
  const notify = message => { status.textContent = message; };
  let blob;
  let previewUrl;
  let activeFormat = 'landscape';
  let imageSource;
  let generation = 0;
  let dismissed = false;

  const copyImage = button('button primary', 'Copy image + caption', async () => {
    if (!blob) return;
    try {
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob, 'text/plain': new Blob([caption], { type: 'text/plain' }) })]);
      notify('Image and caption copied. Paste them into your post.');
    } catch {
      notify('This browser cannot copy an image here. Download the PNG, then copy the caption below.');
      captionField.focus(); captionField.select();
    }
  });
  const nativeShare = button('button', 'Share…', async () => {
    if (!blob) return;
    try { await navigator.share({ files: [new File([blob], `010-${activeFormat}.png`, { type: 'image/png' })], text: caption, title: 'Rotterdam in miniature' }); notify('Shared.'); }
    catch (error) { if (error.name !== 'AbortError') notify('Sharing could not open. Copy or download the image instead.'); }
  });
  nativeShare.hidden = true;
  const download = button('button', 'Download PNG', () => { if (blob) { downloadImage(blob, `010-${activeFormat}.png`); notify('PNG downloaded. Your caption is below.'); } });
  const copyLink = button('button', 'Copy link', async () => {
    try { await navigator.clipboard.writeText(context.link); notify('Link copied. It opens this view and lighting.'); }
    catch { captionField.value = context.link; captionField.focus(); captionField.select(); notify('Select and copy the link below.'); }
  });
  actions.append(copyImage, nativeShare, download, copyLink);
  copyImage.disabled = true; download.disabled = true;

  async function selectFormat(format) {
    const serial = ++generation;
    activeFormat = format;
    formatControls.querySelectorAll('button').forEach(item => { const selected = item.dataset.format === format; item.classList.toggle('selected', selected); item.setAttribute('aria-pressed', selected); });
    copyImage.disabled = true; download.disabled = true; nativeShare.disabled = true;
    previewWrap.classList.add('loading'); notify('Preparing the image…');
    try {
      if (!imageSource) return;
      const prepared = await drawPoster(imageSource, format, context);
      if (serial !== generation || dismissed) return;
      blob = prepared;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(blob); preview.src = previewUrl;
      previewWrap.classList.remove('loading');
      copyImage.disabled = false; download.disabled = false; nativeShare.disabled = false;
      const file = new File([blob], `010-${format}.png`, { type: 'image/png' });
      nativeShare.hidden = !(navigator.share && navigator.canShare?.({ files: [file] }));
      notify(`${FORMATS[format].width} × ${FORMATS[format].height} PNG · no map controls.`);
    } catch (error) { console.error(error); notify('The image could not be prepared. You can still copy the view link.'); }
  }

  for (const [format, details] of Object.entries(FORMATS)) {
    const choice = button('', details.label, () => selectFormat(format)); choice.dataset.format = format;
    choice.setAttribute('aria-pressed', format === activeFormat); choice.classList.toggle('selected', format === activeFormat);
    formatControls.append(choice);
  }
  dialog.append(heading, title, intro, formatControls, previewWrap, actions, captionField, status);
  document.body.append(dialog); dialog.showModal();
  dialog.addEventListener('close', () => { dismissed = true; if (previewUrl) URL.revokeObjectURL(previewUrl); dialog.remove(); });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
  try { imageSource = await captureScene(context.scene); await selectFormat(activeFormat); }
  catch (error) { console.error(error); notify('This view could not be captured. You can still copy its link.'); }
}
