/**
 * Application configuration
 * 
 * Environment variables can be set in:
 * - .env file (for local development)
 * - .env.production (for production builds)
 * 
 * Vite exposes env variables with VITE_ prefix
 */

// Show automated OCR tests button
// Set VITE_SHOW_AUTOMATED_TESTS=false in production to hide the button
export const SHOW_AUTOMATED_TESTS = import.meta.env.VITE_SHOW_AUTOMATED_TESTS !== 'false'

// Default to true (show button) if not explicitly set to false
// This ensures the button is visible during local development

