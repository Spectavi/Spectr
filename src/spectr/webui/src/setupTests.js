import '@testing-library/jest-dom';

// ESM-only markdown dependencies are mocked in Jest to keep CRA tests stable.
jest.mock('react-markdown', () => {
  return function MockReactMarkdown({ children }) {
    return <div>{children}</div>;
  };
});

jest.mock('remark-gfm', () => ({}));
jest.mock('rehype-highlight', () => ({}));
