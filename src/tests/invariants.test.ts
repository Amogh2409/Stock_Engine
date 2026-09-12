/**
 * Asserts the in-app validation suite (the "Unit tests" tab) fully passes.
 * Every check is generated from runAllValidations(), so a validation added
 * there is automatically enforced here.
 */
import { describe, expect, it } from 'vitest';

import { runAllValidations } from '../utils/testRunner';

const results = runAllValidations();

describe('In-app validation suite', () => {
  it('produces a non-empty result set', () => {
    // Guards against the suite silently shrinking to nothing, which would make
    // every generated assertion below vacuous.
    expect(results.length).toBeGreaterThanOrEqual(20);
  });

  for (const result of results) {
    it(`[${result.category}] ${result.name}`, () => {
      expect(result.passed, result.message).toBe(true);
    });
  }
});
