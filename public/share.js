const FORMATS = {
  landscape: { label: 'Landscape', width: 3840, height: 2016, footerHeight: 301, footerScale: 3.2 },
  square: { label: 'Square', width: 2160, height: 2160, footerHeight: 188, footerScale: 2 },
  story: { label: 'Story', width: 2160, height: 3840, footerHeight: 304, footerScale: 2 },
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
  const { width, height, footerHeight, footerScale } = FORMATS[format];
  const imageHeight = height - footerHeight;
  if (source.width !== width || source.height !== imageHeight) {
    throw new Error(`The map capture must be rendered at ${width} × ${imageHeight} pixels.`);
  }
  const canvas = document.createElement('canvas');
  canvas.width = width; canvas.height = height;
  const drawing = canvas.getContext('2d');
  drawing.drawImage(source, 0, 0);
  drawing.fillStyle = '#f2f2e8'; drawing.fillRect(0, imageHeight, width, footerHeight);
  drawing.translate(0, imageHeight);
  drawing.scale(footerScale, footerScale);
  const footerWidth = width / footerScale;
  const footer = footerHeight / footerScale;
  const middle = footer / 2;
  drawing.fillStyle = '#2d473e'; drawing.textBaseline = 'middle';
  drawing.font = '800 51px "Helvetica Neue", Helvetica, sans-serif';
  drawing.fillText('010', 29, middle + 2);
  drawing.fillStyle = '#a5b2a1'; drawing.fillRect(132, middle - 22, 1, 44);
  const label = context.locationLabel === 'Rotterdam' ? 'Rotterdam in miniature' : context.locationLabel;
  drawing.fillStyle = '#2d473e';
  fitText(drawing, label, footerWidth - 480, 24);
  drawing.fillText(label, 157, middle - 11);
  drawing.fillStyle = '#68786b'; drawing.font = '400 13px "Avenir Next", "Segoe UI", sans-serif';
  drawing.fillText('FROM THE CITY TO THE SEA', 158, middle + 16);
  drawing.textAlign = 'right';
  drawing.fillStyle = '#2d473e'; drawing.font = '500 17px "Avenir Next", "Segoe UI", sans-serif';
  drawing.fillText(context.domain, footerWidth - 30, middle - 11);
  drawing.fillStyle = '#68786b'; drawing.font = '400 14px "Avenir Next", "Segoe UI", sans-serif';
  drawing.fillText('by @jjpcodes', footerWidth - 30, middle + 16);
  drawing.textAlign = 'left';
  drawing.font = '400 10px "Avenir Next", "Segoe UI", sans-serif';
  drawing.fillText('Map: Rotterdam · Kadaster / PDOK · AHN / HWH (CC BY 4.0)', 29, footer - 10);
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('The browser could not create the image.')), 'image/png'));
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
  let caption = `Rotterdam in miniature${context.locationLabel !== 'Rotterdam' ? ` · ${context.locationLabel}` : ''}.\nMade by @jjpcodes\n${context.link}`;
  const captionField = element('textarea', 'share-copy'); captionField.readOnly = true; captionField.value = caption; captionField.setAttribute('aria-label', 'Caption and link to copy');
  const status = element('p', 'share-status', 'Preparing the image…'); status.setAttribute('role', 'status');
  const notify = message => { status.textContent = message; };
  let blob;
  let previewUrl;
  let activeFormat = 'landscape';
  let captureQueue = Promise.resolve();
  let generation = 0;
  let dismissed = false;

  const copyImage = button('button primary', 'Copy image + caption', async () => {
    if (!blob) return;
    try {
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob, 'text/plain': new Blob([caption], { type: 'text/plain' }) })]);
      notify('Image and caption copied. Paste them into your post.');
    } catch {
      notify('This browser cannot copy an image here. Download the PNG, then copy the caption below.');
      captionField.value = caption; captionField.focus(); captionField.select();
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
    blob = null;
    formatControls.querySelectorAll('button').forEach(item => { const selected = item.dataset.format === format; item.classList.toggle('selected', selected); item.setAttribute('aria-pressed', selected); });
    copyImage.disabled = true; download.disabled = true; nativeShare.disabled = true;
    previewWrap.hidden = false;
    previewWrap.classList.add('loading'); notify('Rendering the high-resolution image…');
    try {
      const { width, height, footerHeight } = FORMATS[format];
      let capturedView;
      const capture = captureQueue.then(() => {
        if (serial !== generation || dismissed) return null;
        capturedView = context.scene.getView();
        return context.scene.captureCanvas(width, height - footerHeight);
      });
      captureQueue = capture.catch(() => {});
      const imageSource = await capture;
      if (serial !== generation || dismissed) return;
      const prepared = await drawPoster(imageSource, format, context);
      if (serial !== generation || dismissed) return;
      const capturedLink = new URL(context.link);
      capturedLink.searchParams.set('lat', capturedView.lat.toFixed(5));
      capturedLink.searchParams.set('lon', capturedView.lon.toFixed(5));
      capturedLink.searchParams.set('span', Math.round(capturedView.span));
      capturedLink.searchParams.set('bearing', Math.round(capturedView.bearing));
      context.link = capturedLink.toString();
      caption = `Rotterdam in miniature${context.locationLabel !== 'Rotterdam' ? ` · ${context.locationLabel}` : ''}.\nMade by @jjpcodes\n${context.link}`;
      captionField.value = caption;
      blob = prepared;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(blob); preview.src = previewUrl;
      previewWrap.classList.remove('loading');
      copyImage.disabled = false; download.disabled = false; nativeShare.disabled = false;
      const file = new File([blob], `010-${format}.png`, { type: 'image/png' });
      // Native sharing support is optional; a failed capability check must not
      // discard an otherwise usable rendered PNG.
      try { nativeShare.hidden = !(navigator.share && navigator.canShare?.({ files: [file] })); }
      catch { nativeShare.hidden = true; }
      notify(`${FORMATS[format].width} × ${FORMATS[format].height} PNG · no map controls.`);
    } catch (error) {
      if (serial !== generation || dismissed) return;
      console.error(error);
      previewWrap.hidden = true;
      const reason = error.message === 'City detail is still loading. Please try exporting again shortly.'
        ? 'City detail is still loading. Choose a shape to try again shortly.'
        : error.message === 'The requested image size is not supported by this device.'
          ? 'This device cannot render that image size. Try Square.'
          : 'The image could not be prepared. Choose a shape to try again.';
      notify(`${reason} You can still copy the view link.`);
    }
  }

  for (const [format, details] of Object.entries(FORMATS)) {
    const choice = button('', details.label, () => selectFormat(format)); choice.dataset.format = format;
    choice.setAttribute('aria-pressed', format === activeFormat); choice.classList.toggle('selected', format === activeFormat);
    formatControls.append(choice);
  }
  dialog.append(heading, title, intro, formatControls, previewWrap, actions, captionField, status);
  document.body.append(dialog); dialog.showModal();
  dialog.addEventListener('close', () => { dismissed = true; if (previewUrl) URL.revokeObjectURL(previewUrl); dialog.remove(); document.getElementById('share-open')?.focus(); });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
  await selectFormat(activeFormat);
}
