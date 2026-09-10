import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// jsdom does not implement Element.prototype.scrollIntoView
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}
