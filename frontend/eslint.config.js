import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'node_modules']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // Guardrail 1: Prevent god-files from expanding further
      'max-lines': [
        'warn',
        {
          max: 400,
          skipBlankLines: true,
          skipComments: true,
        },
      ],

      // Guardrail 2: Cyclomatic complexity warning
      'complexity': ['warn', { max: 20 }],

      // React hooks relaxation for synchronization effects
      'react-hooks/set-state-in-effect': 'warn',

      // Guardrail 3: Banned arbitrary pixel fonts and hallucinated Tailwind classes
      'no-restricted-syntax': [
        'warn',
        {
          selector: 'JSXAttribute[name.name="className"] > Literal[value=/text-\\[[0-9]+px\\]/]',
          message:
            'Hardcoded pixel text size (text-[...px]) used. Use the @theme type scale tokens (text-2xs, text-xs, text-sm, text-base, text-lg, text-xl) instead.',
        },
        {
          selector: 'JSXAttribute[name.name="className"] TemplateElement[value.raw=/text-\\[[0-9]+px\\]/]',
          message:
            'Hardcoded pixel text size (text-[...px]) used. Use the @theme type scale tokens instead.',
        },
        {
          selector: 'JSXAttribute[name.name="className"] > Literal[value=/(slate-855|slate-550)/]',
          message:
            'Nonexistent Tailwind class (slate-855 / slate-550) used. Use design system tokens from index.css instead.',
        },
        {
          selector: 'JSXAttribute[name.name="className"] TemplateElement[value.raw=/(slate-855|slate-550)/]',
          message:
            'Nonexistent Tailwind class (slate-855 / slate-550) used. Use design system tokens from index.css instead.',
        },
        {
          selector: 'JSXElement > JSXText[value=/[a-zA-Z]{4,}/]',
          message:
            'Potential untranslated copy in JSX. Use useTranslation hook (t(...)) instead of hardcoded text literals.',
        },
      ],
    },
  },
  {
    files: ['**/i18n/**'],
    rules: {
      'max-lines': 'off',
    },
  },
])
