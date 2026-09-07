// Expo Router uses query-string@7, which loads decode-uri-component with CommonJS.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const decodeUriComponent: (input: string) => string = require('../../../vendor/decode-uri-component-cjs');

function encodedRun(value: number): string {
  let remaining = value;
  const bytes: number[] = [];

  for (let index = 0; index < 3; index++) {
    bytes.push(0x20 + (remaining % 95));
    remaining = Math.floor(remaining / 95);
  }

  return bytes.map((byte) => `%${byte.toString(16).padStart(2, '0')}`).join('');
}

describe('decode-uri-component compatibility', () => {
  it('keeps malformed query values readable', () => {
    expect(decodeUriComponent('%E0%A4%A')).toBe('%E0%A4%A');
    expect(decodeUriComponent('%FE%FF%20')).toBe('\uFFFD\uFFFD ');
    expect(decodeUriComponent('%C2')).toBe('\uFFFD');
  });

  it('handles distinct malformed runs without repeated full-string scans', () => {
    const input = Array.from({ length: 40_000 }, (_, index) => `${encodedRun(index)}%G`).join('');
    const startedAt = Date.now();
    const decoded = decodeUriComponent(input);

    expect(decoded).toContain('%G');
    expect(Date.now() - startedAt).toBeLessThan(2_000);
  });
});
