# Suggestions for Improving the Quiz Generation Pipeline

## Overall Assessment

The current fix plan is strong and addresses the core retrieval-leakage problem well.  
Tier A + Tier B should significantly improve quiz quality without disrupting the thesis methodology.

The biggest strengths of the current proposal are:

- Correctly identifying the issue as multi-layered
- Filtering retrieval artifacts before generation
- Reducing diagram/table-label leakage
- Improving prompt constraints
- Preserving methodology traceability (`easy_v1`, `easy_v2`, etc.)
- Avoiding unnecessary overengineering

However, there are still some architectural improvements that could substantially improve question quality long-term.

---

# Additional Suggestions

## 1. Add a Semantic Compression / Abstraction Layer Before Generation

### Why this matters

Even after artifact cleanup, the generation model still receives retrieval in a highly entity-centric format.

Example:

### Raw Retrieval

    Thread 1 waits on semaphore X
    Thread 2 signals semaphore Y
    Output order C A B

This still encourages extractive or lookup-style questions.

### Better Intermediate Representation

    The material explains how semaphores coordinate thread execution order and prevent race conditions in concurrent systems.

This converts retrieval into pedagogical context rather than graph context.

---

## Recommended Pipeline Addition

Current:

    retrieve -> generate question

Recommended:

    retrieve
    -> semantic compression
    -> concept summary
    -> question generation

---

## Suggested Implementation

Add a lightweight preprocessing step before prompt generation.

Example function:

    def compress_retrieval_context(context: RetrievalContext) -> str:
        '''
        Convert raw graph retrieval into a concise conceptual summary
        suitable for educational question generation.
        '''

This does NOT need a separate LLM initially.

Even heuristic summarization would help:

- Remove instance labels
- Merge repetitive entities
- Prioritize explanatory sentences
- Downweight tables/figures
- Collapse BFS traversal noise

---

# 2. Retrieval Should Prefer Concepts Over Labels

## Current Problem

The graph retrieval appears highly entity-centric.

This causes the system to retrieve:

- identifiers
- labels
- node names
- figure references
- table anchors

instead of conceptual explanations.

---

## Recommendation

Introduce concept-oriented reranking.

After graph traversal:

- rank explanatory chunks higher
- rank definition-style passages higher
- rank conceptual paragraphs above tables
- downweight highly structural chunks

---

## Potential Heuristics

Increase score for chunks containing:

- "is defined as"
- "used for"
- "allows"
- "ensures"
- "prevents"
- "manages"
- "coordinates"

Decrease score for chunks dominated by:

- numeric values
- labels
- coordinates
- table structures
- figure references

---

# 3. Add a “Question Intent Planning” Step

## Current Architecture

    retrieve -> generate

## Recommended Architecture

    retrieve
    -> identify concept
    -> identify learning objective
    -> choose question style
    -> generate

---

## Why This Matters

Educational systems should generate questions based on:

- what concept is being tested
- what level of understanding is expected
- what cognitive skill is required

Currently the system appears retrieval-driven rather than pedagogy-driven.

---

## Minimal Version

Before generation:

    question_plan = {
        "concept": "Semaphore synchronization",
        "learning_objective": "Understand synchronization ordering",
        "question_type": "conceptual explanation",
    }

Then generate from the plan.

This alone can dramatically improve question quality.

---

# 4. The Verifier May Be Reinforcing Extractive Behavior

## Important Observation

The current verification criteria appear heavily optimized for:

- answerability from context
- retrieval faithfulness
- low hallucination

This unintentionally rewards lexical overlap and extractive generation.

---

## Problematic Implicit Reward

Current behavior effectively rewards:

    high overlap with retrieval = good

But educational quality requires:

    high conceptual fidelity + low lexical overlap = better

---

## Suggested Additional Verification Checks

Add soft penalties for:

- excessive lexical overlap
- diagram-label dependency
- table-cell extraction
- retrieval artifact leakage
- questions that require the original figure to make sense

---

## Very Useful Heuristic

A strong heuristic:

“Would this question still make sense if the original diagram were removed?”

If not, it is likely too extractive.

---

# 5. Add a Lexical-Overlap Penalty

## Why

Current questions often mirror source wording too closely.

---

## Suggested Metric

Compute similarity between:

- generated question
- retrieved chunk(s)

using:

- Jaccard overlap
- cosine similarity
- token overlap ratio

If overlap exceeds a threshold:

- regenerate
OR
- apply rewrite/paraphrase pass

---

# 6. Easy Difficulty Should Still Be Conceptual

## Current Failure Mode

Easy-mode generation tends to collapse into:

- labels
- values
- identifiers
- lookup facts

---

## Recommendation

Easy questions should still assess understanding.

### Bad

What is the initial value of Semaphore Y?

### Better

Why might a semaphore be initialized to 1 in synchronization problems?

Still easy.
But conceptual.

---

# 7. Prefer Seed Diversity Before Heavy Deduplication

The current proposal correctly avoids expensive embedding-based deduplication early.

The lighter C3 approach is preferable initially.

Reason:

Duplicate questions are likely a symptom of:

- overlapping retrieval
- repetitive chunks
- poor seed diversity

rather than generation failure alone.

---

# 8. Recommended Priority Order

## MUST DO

- Tier A
- Tier B

## HIGH VALUE NEXT STEP

- Semantic compression layer

## LATER IMPROVEMENTS

- question intent planning
- concept clustering
- Bloom taxonomy targeting
- lexical-overlap penalties
- verifier improvements

## AVOID FOR NOW

- full KG redesign
- entity merging/reindexing
- heavy retry loops
- expensive post-generation embedding clustering

---

# Predicted Outcome

## Tier A only

Likely removes:
- most diagram-label questions
- artifact leakage
- structural graph noise

Expected improvement:
~60–70% reduction in obvious bad questions.

---

## Tier A + B

Likely produces:
- acceptable educational questions
- cleaner outputs
- fewer trivial lookups
- fewer tautologies

---

## Tier A + B + Semantic Compression

This is likely where the system begins feeling genuinely intelligent and pedagogically useful.

The compression layer is probably the single highest-leverage long-term improvement.

---

# Final Recommendation

Recommended implementation order:

1. Implement Tier A
2. Implement Tier B
3. Re-run evaluation
4. If quality still feels shallow:
   - add semantic compression layer
5. Only then consider:
   - deduplication
   - advanced verifier logic
   - pedagogical planning

The current proposal is already very strong. The most important missing piece is transforming the system from a retrieval-oriented pipeline into a concept-oriented educational pipeline.
