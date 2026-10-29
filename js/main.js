/* Progressive enhancement: grid links retain full-file/YouTube fallbacks. */
(() => {
  const dialog = document.querySelector('.lightbox');
  const links = Array.from(document.querySelectorAll('a[data-gallery]'));
  if (!dialog || typeof dialog.showModal !== 'function' || !links.length) return;
  const media = dialog.querySelector('.lightbox-media');
  const title = dialog.querySelector('#lightbox-title');
  const status = dialog.querySelector('.lightbox-status');
  const tier = document.createElement('p');
  tier.className = 'lightbox-status lightbox-tier';
  tier.hidden = true;
  title.after(tier);
  const close = dialog.querySelector('[data-close]');
  const previous = dialog.querySelector('[data-prev]');
  const next = dialog.querySelector('[data-next]');
  const youtubeIdPattern = /^[A-Za-z0-9_-]{11}$/;
  let index = 0;
  let trigger = null;
  media.setAttribute('aria-busy', 'false');
  function clear() {
    // Removing the browsing context stops playback; no API/postMessage needed.
    media.replaceChildren();
    media.setAttribute('aria-busy', 'false');
  }
  function display(n) {
    index = (n + links.length) % links.length;
    const link = links[index];
    clear();
    title.textContent = link.dataset.name;
    tier.textContent = link.dataset.tier ? `Tier: ${link.dataset.tier}` : '';
    tier.hidden = !link.dataset.tier;
    const position = `${index + 1} / ${links.length}`;
    previous.disabled = next.disabled = links.length < 2;
    if (link.dataset.kind === 'youtube') {
      const id = link.dataset.youtubeId || '';
      if (id.length !== 11 || !youtubeIdPattern.test(id)) {
        status.textContent = `${position} — No playable YouTube video: this ID is a placeholder or invalid.`;
        return;
      }
      const wrapper = document.createElement('div');
      wrapper.className = 'youtube-frame';
      const frame = document.createElement('iframe');
      frame.title = link.dataset.name;
      frame.allow = 'fullscreen; picture-in-picture';
      frame.allowFullscreen = true;
      frame.referrerPolicy = 'strict-origin-when-cross-origin';
      // Build from the validated ID only; never trust a data URL or href.
      // No autoplay parameter or permission. The visitor presses Play.
      frame.src = `https://www.youtube-nocookie.com/embed/${id}?rel=0&playsinline=1`;
      status.textContent = `${position} — Loading YouTube player…`;
      media.setAttribute('aria-busy', 'true');
      frame.addEventListener('load', () => {
        if (!media.contains(frame)) return;
        media.setAttribute('aria-busy', 'false');
        // Cross-origin load does not prove that YouTube can play this video.
        status.textContent = `${position} — Press Play. If unavailable, check the video on YouTube.`;
      });
      frame.addEventListener('error', () => {
        if (!media.contains(frame)) return;
        media.setAttribute('aria-busy', 'false');
        status.textContent = `${position} — The YouTube player could not be loaded.`;
      });
      wrapper.append(frame);
      media.append(wrapper);
      return;
    }
    if (link.dataset.kind && link.dataset.kind !== 'image') {
      status.textContent = `${position} — Unsupported media type.`;
      return;
    }
    const image = document.createElement('img');
    status.textContent = `${position} — Loading…`;
    media.setAttribute('aria-busy', 'true');
    image.alt = link.dataset.description || link.dataset.name;
    image.decoding = 'async';
    image.addEventListener('load', () => {
      if (!media.contains(image)) return;
      media.setAttribute('aria-busy', 'false');
      status.textContent = position;
    });
    image.addEventListener('error', () => {
      if (!media.contains(image)) return;
      media.setAttribute('aria-busy', 'false');
      status.textContent = 'This file could not be loaded. Close and use the direct link.';
    });
    image.src = link.href;
    media.append(image);
  }
  links.forEach((link, n) => link.addEventListener('click', event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    trigger = link;
    display(n);
    dialog.showModal();
    close.focus();
  }));
  close.addEventListener('click', () => dialog.close());
  previous.addEventListener('click', () => display(index - 1));
  next.addEventListener('click', () => display(index + 1));
  dialog.addEventListener('keydown', event => {
    // For YouTube, use native showModal containment so Tab can enter the iframe.
    if (event.key === 'Tab' && links[index].dataset.kind !== 'youtube') {
      const controls = Array.from(dialog.querySelectorAll('button:not(:disabled)'));
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      return;
    }
    if (event.target.closest('iframe, input, textarea, select')) return;
    if (event.key === 'ArrowLeft') { event.preventDefault(); display(index - 1); }
    if (event.key === 'ArrowRight') { event.preventDefault(); display(index + 1); }
  });
  dialog.addEventListener('close', () => { clear(); if (trigger?.isConnected) trigger.focus(); });
})();
