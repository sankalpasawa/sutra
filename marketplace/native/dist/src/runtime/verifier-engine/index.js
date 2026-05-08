/**
 * VerifierEngine — top-level orchestrator. Wires extractor + verifier +
 * reporter. Constructor takes injectable LLM dispatch + judge dispatch
 * for testability and reuse across Sutra surfaces.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §4
 */
import { extract } from './contract-extractor/extractor.js';
import { verify } from './contract-verifier/verifier.js';
import { formatReport, formatTranscript } from './contract-reporter/reporter.js';
export class VerifierEngine {
    cfg;
    constructor(cfg) {
        this.cfg = cfg;
    }
    extract(utterance) {
        return extract(utterance, this.cfg.llm, { max_retries: this.cfg.max_extract_retries });
    }
    verify(contract, run) {
        return verify(contract, run, { judge: this.cfg.judge });
    }
    format(report, utterance, run) {
        return {
            transcript: formatTranscript(utterance, run),
            report: formatReport(report),
        };
    }
}
export { generateUtterance } from './user-simulator/generate-utterance.js';
//# sourceMappingURL=index.js.map