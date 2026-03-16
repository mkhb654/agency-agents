# RLVR: Reinforcement Learning with Verifiable Rewards — White Paper Research

**Date:** 2026-03-16
**Scope:** Comprehensive survey of RLVR white papers, algorithms, frameworks, and frontier research

---

## Summary

Reinforcement Learning with Verifiable Rewards (RLVR) is the dominant post-training paradigm for building reasoning-capable LLMs as of 2026. Originating with DeepSeek-R1 (January 2025), RLVR replaces learned reward models (RLHF) with deterministic, programmatic verifiers that provide binary or soft reward signals based on objective correctness. The core algorithm powering RLVR is GRPO (Group Relative Policy Optimization), which eliminates the critic network from PPO by using group-level statistics for advantage estimation. The field has rapidly expanded from math/code domains into medicine, chemistry, long-context reasoning, world models, and agentic multi-turn settings. A central academic debate — whether RLVR creates new reasoning capabilities or merely improves sampling efficiency — has converged toward "both," with the CoT-Pass@K metric revealing genuine reasoning quality improvements alongside dominant search compression gains.

---

## 1. Foundational Paper: DeepSeek-R1

**Paper:** "DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning"
- **arXiv:** [2501.12948](https://arxiv.org/abs/2501.12948)
- **Published in:** [Nature](https://www.nature.com/articles/s41586-025-09422-z) (2025)
- **Date:** January 2025

### Key Contributions

- Proved reasoning can be incentivized through **pure RL** without human-labeled reasoning trajectories
- Introduced the RLVR + GRPO combination at production scale
- Demonstrated emergent reasoning behaviors: self-reflection ("Wait, let me reconsider..."), self-verification, dynamic strategy adaptation
- Showed distillation can transfer reasoning capabilities to smaller models (1.5B–70B)
- Performance: competitive with GPT-4 and Claude on math/code benchmarks

### Training Pipeline

**Two-stage approach:**
1. **Cold Start (optional SFT):** Small set of curated long chain-of-thought examples to establish basic reasoning format. DeepSeek-R1-Zero skipped this entirely, proving RL alone suffices.
2. **RLVR Training:** Pure RL with two reward types:
   - Accuracy reward: Binary signal from verifier (correct = 1, incorrect = 0)
   - Format reward: Checks structural compliance (thinking tags, answer formatting)

### GRPO Algorithm

Group Relative Policy Optimization eliminates the critic network from PPO:

- **Advantage estimation:** `A_i = (r_i - mean(group_rewards)) / (std(group_rewards) + epsilon)`
- **Surrogate loss:** `L = min(A * ratio, A * clip(ratio, 1-eps, 1+eps)) - beta * KL_div`
- **KL divergence (DeepSeekMath variant):** `KL ≈ exp(ref_logprobs - policy_logprobs) - (ref_logprobs - policy_logprobs) - 1` (guarantees non-negative values)

**Training hyperparameters:** LR 3e-6, KL coefficient 0.001, clip ratio 10, temperature 1.0, 16 samples per question, max length 32,768 tokens, batch size 512 (32 questions × 16 outputs).

### Distillation Results

6 distilled models released, trained via SFT on 800,000 reasoning samples from DeepSeek-R1:

| Model | Base | Size |
|-------|------|------|
| DeepSeek-R1-Distill-Qwen-1.5B | Qwen2.5-1.5B | 1.5B |
| DeepSeek-R1-Distill-Qwen-7B | Qwen2.5-7B | 7B |
| DeepSeek-R1-Distill-Qwen-14B | Qwen2.5-14B | 14B |
| DeepSeek-R1-Distill-Qwen-32B | Qwen2.5-32B | 32B |
| DeepSeek-R1-Distill-Llama-8B | Llama3.1-8B | 8B |
| DeepSeek-R1-Distill-Llama-70B | Llama3.3-70B | 70B |

Critical finding: Distilled models often outperform models trained with large-scale RL at lower computational cost.

---

## 2. The Debate: Efficiency vs Intelligence

### The Skeptical View

**Paper:** "Does RL Really Incentivize Reasoning Capability in LLMs? A Computational Analysis"
- **arXiv:** [2504.13837](https://arxiv.org/abs/2504.13837)
- **Authors:** Tsinghua University (LeapLab)
- **Venue:** NeurIPS 2025
- **Code:** [github.com/LeapLabTHU/limit-of-RLVR](https://github.com/LeapLabTHU/limit-of-RLVR)

**Findings:**
- RLVR does NOT create fundamentally new reasoning patterns
- At large k, base models achieve **higher** pass@k than RLVR-trained versions
- All reasoning paths in RLVR models already exist in the base model's distribution
- ~71% of improvement comes from better output selection, not deeper thinking
- RLVR = sampling efficiency improvement, not capability expansion
- Knowledge distillation genuinely expands reasoning capabilities (unlike RLVR)
- Six popular RLVR algorithms perform similarly and remain far from optimal

### The Rebuttal

**Paper:** "Reinforcement Learning with Verifiable Rewards Implicitly Incentivizes Correct Reasoning in Base LLMs"
- **arXiv:** [2506.14245](https://arxiv.org/abs/2506.14245)
- **Authors:** Xumeng Wen, Zihan Liu, Shun Zheng, Shengyu Ye, Zhirong Wu, Yang Wang, Zhijian Xu, Xiao Liang, Junjie Li, Ziming Miao, Jiang Bian, Mao Yang
- **Date:** June 2025

**Key contributions:**
- Introduced **CoT-Pass@K** metric: accounts for both correct reasoning AND correct answers (not just final answer correctness)
- Standard Pass@K is misleading because base LLMs generate "inaccurate or incomplete chains-of-thought that coincidentally arrive at correct solutions"
- With CoT-Pass@K, RLVR shows **persistent and significant gap** across all K values (up to 1024)

**Theoretical Framework (Theorem 1):**
Under logical coherence assumption P(Answer=1|CoT=1) = α > P(Answer=1|CoT=0) = β:
- E[Advantage | correct CoT] > 0
- E[Advantage | incorrect CoT] < 0
- GRPO gradients inherently increase probability of correct reasoning chains

**Training dynamics observation:** P(correct CoT | correct answer) increases monotonically during training, even as P(correct answer) plateaus — orthogonal improvement in reasoning quality.

### Emerging Consensus (2026)

The reality is **both**:
- ~60-70% of gains: Search compression / sampling efficiency
- ~30-40% of gains: Genuine reasoning quality improvement
- CoT-Pass@K provides a more honest picture than standard Pass@K

---

## 3. GRPO Mathematical Analysis

**Paper:** "Reinforcement Learning with Verifiable Rewards: GRPO's Effective Loss, Dynamics, and Success Amplification"
- **arXiv:** [2503.06639](https://arxiv.org/abs/2503.06639)
- **Author:** Youssef Mroueh
- **Date:** March 2025

### Technical Framework

- Mean + variance calibration of binary rewards induces a **weighted contrastive loss** where contrastive samples are synthetic data drawn from the previous policy
- Derived **closed-form expressions** for optimal policy π_n depending on: binary reward values, first and second-order reward statistics under π_{n-1}, and previous/reference policies
- The iterative sequence {π_n} follows a **probability-of-success (PoS) recurrence relation** that converges to a fixed point exceeding the reference model's baseline
- Three regularization approaches studied: KL from previous model, KL from fixed reference, or both — each producing distinct convergence behaviors

### Optimization Theory: Gradient Gap Framework

**Paper:** [arXiv:2510.08539](https://arxiv.org/html/2510.08539v3) (October 2025)

**Core concept:** The Gradient Gap is the difference between expected score gradients in positive (correct) vs negative (incorrect) response regions.

**Key theorems:**
1. **Convergence:** When step sizes satisfy `η ≤ [Δμq(k)]₊ / 2(L_o + 8G²_o)`, performance improves monotonically
2. **Catastrophic Failure:** Even with perfect alignment, oversized step sizes cause performance to strictly decrease every iteration
3. **Token-Level:** Step size must shrink proportionally to response length T, success rate (1-J_q), and token regularity bounds

**Convergence rate:**
```
J_q(K) ≥ J_q(0) / [J_q(0) + {1-J_q(0)} · exp(-M_q(K)/2)]
```
Where `M_q(K) = Σ[Δμq(k)]₊ηk` = cumulative progress.

**Practical implications:**
- Use smaller learning rates for longer responses
- Don't chase 100% accuracy — natural plateau near perfection due to variance normalization artifacts
- Length normalization is not optional — theory proves it's necessary for convergence

---

## 4. GRPO Variant Algorithms

### DAPO (Decoupled Clip and Dynamic Sampling Policy Optimization)

- **arXiv:** [2503.14476](https://arxiv.org/abs/2503.14476)
- **Origin:** ByteDance Seed, March 2025
- **Result:** 50 points on AIME 2024 with Qwen2.5-32B using **50% fewer training steps**

Four techniques:
1. **Clip-Higher:** Asymmetric clipping [0.8, 1.28] — prevents entropy collapse
2. **Dynamic Sampling:** Over-samples until each group has both correct AND incorrect responses
3. **Token-level Policy Gradient Loss:** Normalizes by total group tokens, not per-sample
4. **Overlong Reward Shaping:** Soft length penalty (ramp, not cliff)

### Dr. GRPO (GRPO Done Right)

Corrects three biases in vanilla GRPO:
- Removes `1/|o_i|` length normalization (creates asymmetric learning)
- Eliminates `std()` normalization (causes difficulty-based reweighting)
- Prevents length-bias artifacts

### GSPO (Group Sequence Policy Optimization)

Moves from token-level to **sequence-level** importance ratios: `s_i(θ) = (π_θ(y_i|x) / π_old(y_i|x))^(1/|y_i|)`. Geometric mean per token maintains numeric stability across long responses.

### CISPO (Clipped IS-weight Policy Optimization)

Clips importance weights themselves rather than update magnitudes. Stop-gradient prevents second-order instabilities. Keeps rare reasoning tokens (like "Wait," "However") active across multiple off-policy update rounds.

### SAPO (Soft Adaptive Policy Optimization)

Replaces hard clipping with temperature-controlled smooth gates: `f_i,t(r) = (4/τ)σ(τ(r-1))`. Uses `τ_neg > τ_pos` because negative-advantage updates diffuse probability mass across massive vocabulary space.

### RSPO (Router-Shift Policy Optimization)

MoE-specific: Handles routing distribution shifts between updates with drift penalty `γ_i,t = exp(-avg_routing_change)`.

### GMPO (Geometric Mean Policy Optimization)

Aggregates via geometric mean: `(∏_t |ρ_i,t × Â_i|)^(1/|o_i|)`. Naturally contains extreme values in log-space.

### Unified Framework

All methods fit: `J(θ) = E[f_i,t(r_i,t(θ)) × Â_i,t]` where f differs per algorithm.

| Algorithm | Best For | Key Advantage |
|-----------|----------|---------------|
| GRPO | General purpose | Simplest, well-understood |
| DAPO | Long CoT reasoning, math | 50% fewer steps, entropy preservation |
| Dr. GRPO | Length bias problems | Corrects known GRPO biases |
| GSPO | Very long outputs | Sequence-level stability |
| CISPO | Multi-epoch off-policy | Keeps rare reasoning tokens alive |
| SAPO | Smooth training | No hard clipping artifacts |
| RSPO | Mixture-of-Experts | Handles routing instability |

---

## 5. Training Recipes

### JustRL: The Minimalist Recipe (ICLR 2026)

- **Source:** [ICLR 2026 Blog Post](https://iclr-blogposts.github.io/2026/blog/2026/justrl/)

Single-stage, no-frills approach matching complex multi-stage pipelines.

| Parameter | Value |
|-----------|-------|
| Algorithm | GRPO (no modifications) |
| Learning Rate | 1e-6 (constant) |
| Train Batch Size | 256 |
| Mini Batch Size | 64 |
| Clip Ratio | [0.8, 1.28] (asymmetric) |
| Temperature | 1.0 (fixed) |
| Rollout N | 8 |
| Max Response Length | 15,000 tokens |
| KL Coefficient | **0.0** (no KL penalty) |
| Training Steps | ~3,400-4,400 |
| Hardware | 32× A800-80GB (~15 days) |

**Data:** DAPO-Math-17k dataset. **Verifier:** Rule-based + CompassVerifier-3B.

**Results:**
- JustRL-Nemotron-1.5B: 64.32% avg across 9 benchmarks, 69.69% AIME 2024
- Uses 2× less compute than ProRL-V2

**Key insight:** KL coefficient = 0 works best — the verifiable reward signal is clean enough that KL regularization is unnecessary.

---

## 6. Domain Expansion

### Cross-Domain RLVR

**Paper:** "Crossing the Reward Bridge: Expanding RL with Verifiable Rewards Across Diverse Domains"
- **arXiv:** [2503.23829](https://arxiv.org/abs/2503.23829)
- **Authors:** Yi Su, Dian Yu, Linfeng Song, Juntao Li, Haitao Mi, Zhaopeng Tu, Min Zhang, Dong Yu
- **Date:** March 2025

**Contributions:**
- Extended RLVR beyond math/code to medicine, chemistry, psychology, economics, education
- Binary verification judgments show high consistency across LLMs when expert reference answers exist
- **Generative scoring** (soft rewards from 7B models) overcomes binary verification limitations in free-form domains
- Outperformed Qwen2.5-72B and DeepSeek-R1-Distill-Qwen-32B across domains
- Proved cross-domain reward models work without extensive domain-specific annotation

### Rubrics as Rewards

**Paper:** [arXiv:2507.17746](https://arxiv.org/abs/2507.17746) (July 2025)

Extends RLVR to non-verifiable domains using rubric-based feedback. "Judge Code" programmatically translates evaluation rubrics into executable verification.

### Domain Applicability Map

| Domain | Verification Method | Signal Type |
|--------|-------------------|-------------|
| Math | Exact answer matching | Binary |
| Code | Test case execution | Binary |
| Logic puzzles | Rule checking | Binary |
| Text2SQL | Query execution + result comparison | Binary |
| Medicine | Generative scoring / guideline verification | Soft |
| Chemistry | Expert reference + LLM-as-judge | Soft |
| Psychology | Rubric-based evaluation code | Soft |
| Education | Auto-generated judge code | Soft |
| Creative writing | No ground truth — use RLHF/DPO | N/A |

---

## 7. Long-Context RLVR

**Paper:** "LongRLVR: Long-Context Reinforcement Learning Requires Verifiable Context Rewards"
- **arXiv:** [2603.02146](https://arxiv.org/abs/2603.02146)
- **Authors:** Guanzheng Chen, Michael Qizhe Shieh, Lidong Bing
- **Date:** March 2026

### Problem

Standard RLVR falters in long-context scenarios because:
- Reliance on internal parametric knowledge is ill-suited for tasks requiring contextual grounding
- A reward based solely on the final answer is too sparse to guide evidence identification
- Outcome-only rewards lead to vanishing gradients for the context grounding process

### Solution

LongRLVR augments sparse answer-based rewards with **dense, verifiable context rewards** that directly incentivize the model to select correct grounding information.

### Results

| Benchmark | Standard RLVR | LongRLVR |
|-----------|--------------|----------|
| RULER-QA (14B) | 73.17 | **88.90** |
| LongBench v2 (14B) | 39.8 | **46.5** |

### Related Work

- **Document Reconstruction Unlocks Scalable Long-Context RLVR** ([arXiv:2602.08237](https://arxiv.org/abs/2602.08237))
- **LongR: Unleashing Long-Context Reasoning via RL with Dense Utility Rewards** ([arXiv:2602.05758](https://arxiv.org/abs/2602.05758))

---

## 8. Noisy Rewards and Imperfect Verifiers

**Paper:** "Reinforcement Learning with Verifiable yet Noisy Rewards under Imperfect Verifiers"
- **arXiv:** [2510.00915](https://arxiv.org/abs/2510.00915)
- **Date:** October 2025

### Problem

Verifiers are systematically fallible in two opposing ways:
- **False positives:** Accept incorrect solutions → rewards hackable patterns
- **False negatives:** Reject correct ones → deprives agent of informative gradients

### Corrections

Two lightweight corrections derived from formalizing verifier unreliability as a stochastic reward channel with asymmetric noise rates:
1. **Backward correction:** Yields an unbiased surrogate reward
2. **Forward correction:** Reweights score-function terms so expected update aligns with clean gradient direction

### Related: RLVεR

**Paper:** "Rate or Fate? RLVεR: Reinforcement Learning with Verifiable Noisy Rewards"
- **arXiv:** [2601.04411](https://arxiv.org/abs/2601.04411)

---

## 9. Unsupervised RLVR

**Paper:** "How Far Can Unsupervised RLVR Scale LLM Training?"
- **arXiv:** [2603.08660](https://arxiv.org/abs/2603.08660)
- **Date:** March 2026

### Key Findings

- Classifies URLVR methods into **intrinsic** vs **external** based on reward sources
- All intrinsic methods converge toward **sharpening the model's initial distribution**
- Sharpening succeeds when initial confidence aligns with correctness, fails catastrophically when misaligned
- **INTUITOR** uses a model's intrinsic self-certainty as its sole reward signal — matches supervised RLVR on math reasoning and achieves competitive OOD generalization

### Significance

Represents a frontier for scaling RLVR beyond the supervision bottleneck — no ground-truth labels needed.

---

## 10. Process Rewards vs Outcome Rewards

### Verification Granularity Spectrum

| Level | What's Verified | Signal |
|-------|----------------|--------|
| Outcome (ORM) | Final answer only | Binary |
| Process (PRM) | Each intermediate step | Per-step score |
| Verifiable Process (VPRM) | Each step via deterministic rules | Per-step binary |

### Verifiable Process Reward Models (VPRMs)

- **arXiv:** [2601.17223](https://arxiv.org/abs/2601.17223)
- Replace neural step judges with deterministic rule-based verifiers per step
- Application: Medical evidence synthesis with guideline-defined criteria
- Results: +20% F1 over SOTA, +6.5% F1 over outcome-only verification

---

## 11. Multi-Turn RLVR & Agentic RL

### VerlTool Framework

- **arXiv:** [2509.01055](https://arxiv.org/abs/2509.01055) (September 2025)
- Formalizes **Agentic RL with Tool use (ARLT)** as multi-turn trajectories with multi-modal observation tokens
- Built on veRL framework; supports 6 domains: math reasoning, knowledge QA, SQL, visual reasoning, web search, software engineering
- Async rollout execution → near 2× speedup (GPUs don't idle during tool calls)

### Related Agentic Frameworks

| Framework | Focus | Key Metric |
|-----------|-------|------------|
| VerlTool | Multi-domain tool use | 2× throughput |
| NeMo Gym | Interactive environments | 1.2M rollouts, 21 configs |
| RLFactory | Multi-round tool-use | 6.8× throughput |
| MOSAIC | Safety-focused agentic training | 50% reduction in harmful behavior |

---

## 12. RLVR Beyond Language: World Models

**Paper:** "RLVR-World"
- **arXiv:** [2505.13934](https://arxiv.org/abs/2505.13934)
- **Venue:** NeurIPS 2025
- **Code:** [github.com/thuml/RLVR-World](https://github.com/thuml/RLVR-World)

Uses RLVR to directly optimize world models for task-specific prediction metrics rather than maximum likelihood estimation.

| Domain | Metric | Improvement |
|--------|--------|-------------|
| Text games | State accuracy | +30.7% |
| Web navigation | F1 score | +15.1% |
| WebArena agents | Success rate | +18.4% |
| Robot manipulation | LPIPS | +9.2% |

---

## 13. Safety & Alignment

### HarmRLVR: RLVR as Attack Vector

Safety alignment can be rapidly reversed using GRPO with **merely 64 harmful prompts** (without responses). The model learns to comply with harmful instructions while preserving general capabilities.

### Defense Approaches

| Defense | Method |
|---------|--------|
| ReAlign | Safety verifier feedback + general reward model + refusal penalty |
| SafeWork-R1 | Dedicated verifiers for safety compliance + knowledge soundness at 1000-GPU scale |
| R1-ACT | Activates existing safety knowledge through structured reasoning (no retraining) |

---

## 14. Open-Source Frameworks

| Framework | Origin | Architecture | Best For |
|-----------|--------|-------------|----------|
| TRL | HuggingFace | HF ecosystem integration | Quick prototyping |
| veRL | ByteDance | Dual-mode (HybridEngine + AsyncServer) | Production scale, tool-use RL |
| OpenRLHF | Open source | Ray-based, separate resource pools | Newcomers, production reliability |
| AReaL | Ant Research | Fully decoupled async | Maximum throughput (2-3× gains) |
| LlamaRL | Meta | Single controller, DDMA GPU-direct | 405B+ scale |
| Slime | Tsinghua/Zhipu | Three services + HTTP APIs | SGLang integration |

**Critical bottleneck:** 80-90% of training time is sample generation (rollouts). Every major framework innovation targets this.

---

## 15. Scaling Laws

### Sigmoid Learning Curves (ScaleRL)

- Rapid initial gains (~80% of improvements in first quarter)
- Gradual saturation toward asymptote
- Can predict final performance using ~25% of planned compute

### Model Size vs RL Compute

- Larger base models demonstrate significantly better RLVR scaling
- A 17B×16 MoE achieves higher asymptotic RL performance than 8B dense using only **1/6 of RL training compute**
- Implication: Invest in larger base model before more RL compute

### Open Questions

- No public evidence RLVR usefully scales beyond modest training amounts
- Generalization beyond competition math/coding unproven at scale
- Optimal base-model-size-to-RL-compute ratio unknown

---

## 16. The Modern Post-Training Stack (2026)

```
Pretrain → SFT → Preference Optimization (DPO/SimPO/KTO) → RLVR (GRPO/DAPO)
```

| Stage | Purpose | Signal |
|-------|---------|--------|
| SFT | Instruction following, format | Human demonstrations |
| Preference | Alignment, safety, style | Preference pairs |
| RLVR | Reasoning, correctness | Verifiable rewards |

**Key insight:** GRPO can improve beyond training data (online RL generates novel solutions), while DPO is bounded by the quality of preference pairs.

**Optimal pipeline:** Distillation (introduces new reasoning patterns) → RLVR (optimizes sampling efficiency for those patterns).

---

## Complete Source Index

### Foundational Papers
1. [DeepSeek-R1: Incentivizing Reasoning via RL](https://arxiv.org/abs/2501.12948) — January 2025
2. [Does RL Really Incentivize Reasoning? (Tsinghua)](https://arxiv.org/abs/2504.13837) — April 2025, NeurIPS 2025
3. [RLVR Implicitly Incentivizes Correct Reasoning](https://arxiv.org/abs/2506.14245) — June 2025

### Algorithm Analysis
4. [GRPO's Effective Loss, Dynamics, and Success Amplification](https://arxiv.org/abs/2503.06639) — March 2025
5. [DAPO: Open-Source LLM RL at Scale](https://arxiv.org/abs/2503.14476) — March 2025
6. [RLVR Optimization Dynamics: Gradient Gap](https://arxiv.org/html/2510.08539v3) — October 2025

### Domain Expansion
7. [Crossing the Reward Bridge](https://arxiv.org/abs/2503.23829) — March 2025
8. [Rubrics as Rewards](https://arxiv.org/abs/2507.17746) — July 2025
9. [LongRLVR: Long-Context RL with Verifiable Context Rewards](https://arxiv.org/abs/2603.02146) — March 2026
10. [Document Reconstruction for Long-Context RLVR](https://arxiv.org/abs/2602.08237) — February 2026

### Robustness & Scaling
11. [RLVR with Noisy Rewards under Imperfect Verifiers](https://arxiv.org/abs/2510.00915) — October 2025
12. [RLVεR: Verifiable Noisy Rewards](https://arxiv.org/abs/2601.04411) — January 2026
13. [How Far Can Unsupervised RLVR Scale?](https://arxiv.org/abs/2603.08660) — March 2026

### Process Rewards & Verification
14. [Verifiable Process Reward Models (VPRMs)](https://arxiv.org/abs/2601.17223) — January 2026
15. [SPARK: Stepwise Process-Aware Rewards](https://arxiv.org/html/2512.03244) — December 2025

### Multi-Turn & Agentic
16. [VerlTool: Agentic RL with Tool Use](https://arxiv.org/abs/2509.01055) — September 2025

### World Models & Beyond Language
17. [RLVR-World (NeurIPS 2025)](https://arxiv.org/abs/2505.13934) — May 2025

### Safety & Alignment
18. [HarmRLVR: Weaponizing Verifiable Rewards](https://www.alphaxiv.org/overview/2510.15499v1) — October 2025
19. [ReAlign: Safety-Aligning Reasoning Models](https://openreview.net/forum?id=XxYNlbTFYS)
20. [R1-ACT: Activating Safety Knowledge](https://arxiv.org/abs/2508.00324) — August 2025
21. [SafeWork-R1: Coevolving Safety and Intelligence](https://arxiv.org/pdf/2507.18576) — July 2025

### Training Recipes
22. [JustRL: Scaling 1.5B with Simple RL (ICLR 2026)](https://iclr-blogposts.github.io/2026/blog/2026/justrl/)
23. [Re-Distilling DeepSeek R1 Models (Dropbox)](https://dropbox.github.io/r1_redistill_blogpost/)

### Technical Overviews
24. [GRPO Explained (Cameron Wolfe)](https://cameronrwolfe.substack.com/p/grpo)
25. [State of LLM Reasoning (Sebastian Raschka)](https://magazine.sebastianraschka.com/p/the-state-of-llm-reasoning-model-training)
26. [RLVR Explained (Promptfoo)](https://www.promptfoo.dev/blog/rlvr-explained/)
27. [RLVR Beyond SFT (Fireworks)](https://fireworks.ai/blog/reinforcement-learning-with-verifiable-reward)
28. [Unsloth RL Guide](https://unsloth.ai/docs/get-started/reinforcement-learning-rl-guide)

### Frameworks
29. [veRL Documentation](https://verl.readthedocs.io/en/latest/algo/grpo.html)
30. [OpenRLHF](https://arxiv.org/html/2501.03262v4)
31. [DeepSeek-R1 Build from Scratch (GitHub)](https://github.com/FareedKhan-dev/train-deepseek-r1)
