/**
 * Detect iOS (iPhone/iPad/iPod). On iOS the native file picker already offers
 * Camera + Photo Library, so we skip our in-app camera/gallery chooser there.
 * iPadOS 13+ masquerades as Mac, so also treat a touch-capable Mac as iOS.
 */
export function isIOS(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  if (/iP(hone|ad|od)/.test(ua)) return true;
  return ua.includes('Mac') && typeof document !== 'undefined' && 'ontouchend' in document;
}
