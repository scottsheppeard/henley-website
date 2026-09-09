/// <reference types="astro/client" />

declare global {
  interface Window {
    /**
     * Google Tag Manager's queue.
     *
     * Declared here because the thank-you page pushes the enquiry conversion
     * into it, and does so by creating the array if the container has not
     * loaded yet — so the event survives a slow or blocked GTM rather than
     * being dropped.
     */
    dataLayer: Record<string, unknown>[];
  }
}

export {};
