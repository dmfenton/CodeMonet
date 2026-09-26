import js from '@eslint/js';
import eslintReact from '@eslint-react/eslint-plugin';
import eslintConfigPrettier from 'eslint-config-prettier';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

const sourceFiles = ['{shared,web}/**/*.{ts,tsx}'];
const reactErrorRules = Object.fromEntries(
  Object.entries(eslintReact.configs.recommended.rules).filter(([, setting]) => {
    const severity = Array.isArray(setting) ? setting[0] : setting;
    return severity === 'error' || severity === 2;
  })
);

export default [
  {
    ignores: ['**/node_modules/**', '**/dist/**', '**/coverage/**'],
  },
  {
    files: sourceFiles,
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        ecmaVersion: 'latest',
        projectService: true,
        sourceType: 'module',
        tsconfigRootDir: import.meta.dirname,
      },
      globals: {
        __DEV__: 'readonly',
        ...globals.browser,
        ...globals.es2025,
        ...globals.jest,
        ...globals.node,
      },
    },
    plugins: {
      ...eslintReact.configs.recommended.plugins,
      '@typescript-eslint': tseslint.plugin,
      'react-hooks': reactHooks,
    },
    settings: eslintReact.configs.recommended.settings,
    rules: {
      ...js.configs.recommended.rules,
      ...tseslint.plugin.configs.recommended.rules,
      ...reactErrorRules,
      ...eslintConfigPrettier.rules,
      'no-undef': 'off',
      'no-useless-assignment': 'off',
      '@eslint-react/static-components': 'off',
      'react-hooks/exhaustive-deps': 'error',
      'react-hooks/rules-of-hooks': 'error',
      '@typescript-eslint/explicit-function-return-type': 'off',
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  {
    files: ['web/src/test/**/*.ts', 'web/src/**/*.test.{ts,tsx}'],
    languageOptions: {
      parserOptions: { projectService: false },
    },
  },
];
