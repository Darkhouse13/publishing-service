import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        base: '#000000',
        panel: '#f2f1eb',
        accent: '#ffcc00',
        muted: '#666666',
        error: '#ff4444',
      },
      boxShadow: {
        'solid-sm': '4px 4px 0px 0px rgba(0, 0, 0, 1)',
        'solid-md': '8px 8px 0px 0px rgba(0, 0, 0, 1)',
        'solid-lg': '12px 12px 0px 0px rgba(0, 0, 0, 1)',
      },
      borderRadius: {
        none: '0px',
      },
      fontFamily: {
        sans: ['Helvetica Neue', 'Helvetica', 'Arial', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
