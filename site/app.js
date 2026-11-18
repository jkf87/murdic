const english = document.documentElement.lang === "en";
const video = document.querySelector("video");
const sound = document.querySelector("#sound");

function updateSound() {
  sound.textContent = video.muted
    ? english
      ? "Turn sound on"
      : "소리 켜기"
    : english
      ? "Mute sound"
      : "소리 끄기";
  sound.setAttribute("aria-pressed", String(!video.muted));
}

sound.addEventListener("click", () => {
  video.muted = !video.muted;
  if (!video.muted && video.paused) video.play().catch(() => {});
  updateSound();
});
video.addEventListener("volumechange", updateSound);
video.addEventListener("error", () => {
  sound.hidden = true;
});
if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
  video.autoplay = false;
  video.pause();
}

const copy = document.querySelector(".copy");
copy.addEventListener("click", async () => {
  const code = document.querySelector("pre code");
  try {
    await navigator.clipboard.writeText(code.textContent);
    copy.textContent = english ? "Copied" : "복사됨";
  } catch {
    const range = document.createRange();
    range.selectNodeContents(code);
    const selection = getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    copy.textContent = english ? "Press ⌘C" : "⌘C로 복사";
  }
});
