import type { Config } from 'tailwindcss';

export default <Config>{
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './pages/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        'bg-base': '#EEEEEE',
        'text-main': '#1F6F5F',
        'primary': '#2FA084',
        'accent': '#6FCF97',
      },
    },
  },
  plugins: [],
};
