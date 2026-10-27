import { describe, expect, it, vi } from "vitest";
import { answerFrozenApproval } from "./approvalDecision.js";

const approval = { id: "appr_1", proposal: { digest: "a".repeat(64) }, judge: { risk: "red" } };

describe("answerFrozenApproval", () => {
  it("takes a WebAuthn step-up bound to the ID and digest before sending a red approval", async () => {
    const events = [];
    const secondFactor = { stepUp: vi.fn(async () => { events.push("step-up"); return { token: "once" }; }) };
    const argus = { answerApproval: vi.fn(async () => { events.push("answer"); return { state: "approved" }; }) };
    await answerFrozenApproval({ approval, decision: "approved", confirmation: "vm-166/container:argus-lab-cache",
      reason: "", secondFactor, argus });
    expect(events).toEqual(["step-up", "answer"]);
    expect(secondFactor.stepUp).toHaveBeenCalledWith(`approval:appr_1:${approval.proposal.digest}`);
    expect(argus.answerApproval).toHaveBeenCalledWith("appr_1", {
      decision: "approved", proposalDigest: approval.proposal.digest, stepUpToken: "once",
      confirmationTarget: "vm-166/container:argus-lab-cache", reason: null,
    });
  });

  it("sends a denial with its trimmed reason and no confirmation", async () => {
    const secondFactor = { stepUp: vi.fn(async () => ({ token: "once" })) };
    const argus = { answerApproval: vi.fn(async () => ({ state: "denied" })) };
    await answerFrozenApproval({ approval, decision: "denied", confirmation: "x", reason: "  owner restoring  ",
      secondFactor, argus });
    expect(argus.answerApproval).toHaveBeenCalledWith("appr_1", {
      decision: "denied", proposalDigest: approval.proposal.digest, stepUpToken: "once",
      confirmationTarget: null, reason: "owner restoring",
    });
  });

  it("never sends an answer when the step-up fails", async () => {
    const argus = { answerApproval: vi.fn() };
    const secondFactor = { stepUp: vi.fn(async () => { throw new Error("cancelled"); }) };
    await expect(answerFrozenApproval({ approval, decision: "denied", confirmation: "", secondFactor, argus })).rejects.toThrow("cancelled");
    expect(argus.answerApproval).not.toHaveBeenCalled();
  });
});
