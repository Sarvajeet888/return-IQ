// Vitest setup — runs before every test file.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  // Unmount React trees between tests. Without this, a component that sets
  // an interval or subscribes to something keeps running into the next test
  // and produces failures that look unrelated to the code that caused them.
  cleanup()
  // localStorage persists across tests in jsdom. Auth tests write to it, so
  // leaving it dirty makes test outcomes depend on execution order — the
  // single most confusing class of test failure to debug.
  localStorage.clear()
  vi.restoreAllMocks()
})

// jsdom does not implement matchMedia, and components that check for reduced
// motion or breakpoints will throw without it.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })
}
