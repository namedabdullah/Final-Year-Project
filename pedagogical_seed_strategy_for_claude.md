# Pedagogical Seed Selection Strategy
## Implementation Notes for Claude Code

---

# Core Recommendation

Use a hybrid ranking system rather than an LLM-only approach.

```text
Pedagogical Score
=
Structural Signals
+
Document Signals
+
Optional LLM Score
```

The LLM should be a refinement layer, not the primary selector.

This provides:
- lower cost
- lower latency
- more explainable behavior
- stronger research justification

---

# Goal 1: Meaningful Seeds (GraphRAG)

GraphRAG already operates on entities.

For every entity, compute:

```text
Entity Score
=
0.4 × Centrality
+
0.3 × Cross-Document Presence
+
0.2 × Frequency
+
0.1 × LLM Importance
```

## Centrality

Potential signals:
- Degree Centrality
- PageRank
- Graph Neighbors
- Betweenness Centrality

Example:

```text
TCP               0.92
UDP               0.88
Checksum          0.55
Table 3           0.01
```

Higher values indicate more important concepts.

## Cross-Document Presence

Count how many selected files mention the entity.

Example:

```text
TCP appears in 4 files → score = 4
Round Robin appears in 1 file → score = 1
```

Concepts appearing across multiple files are often foundational and worth learning.

## Frequency

Count total mentions.

Example:

```text
TCP: 41 mentions
UDP: 28 mentions
Checksum: 3 mentions
```

## Optional LLM Layer

Apply only to the top-ranked candidates (e.g., Top-50).

Prompt:

```text
Rank these concepts by educational importance.

Consider:
- foundational importance
- usefulness for learning
- prerequisite knowledge
- likelihood of appearing in an assessment

Return a score from 1-10.
```

The LLM should act as a final educational ranking signal rather than the primary selector.

---

# Goal 2: Meaningful Chunks (Naive RAG)

Chunk centrality is difficult to compute directly.

Instead use content quality signals.

## Concept Density

Count:
- Named entities
- Technical concepts
- Key phrases

Example:

```text
TCP reliability
Acknowledgements
Retransmissions
Flow control
```

High concept density usually indicates strong educational content.

## Explanatory Density

Look for explanatory language such as:

```text
is defined as
refers to
because
therefore
consists of
unlike
compared to
```

## Noise Penalty

Downweight or remove:

```text
tables
captions
references
bibliography
appendix
metadata
```

## Chunk Score

```text
Chunk Score
=
Concept Density
+
Explanatory Density
+
Cross-Document Relevance
-
Noise Penalty
```

---

# Goal 3: Diversity

Many quiz systems fail because they repeatedly select highly related concepts.

## Example of Poor Diversity

```text
TCP
TCP Reliability
TCP Acknowledgements
TCP Retransmission
TCP Window Size
```

## Semantic Diversity Filter

After ranking:

1. Select the best candidate.
2. Reject candidates that are too similar to already-selected concepts.


Desired outcome:

```text
TCP
UDP
Packet Loss
Congestion Control
Streaming
```

---

# Goal 4: Cross-Document Contribution

Do not force:

```text
1 question per file
```

This may introduce low-quality content from weak files.

## Better Approach

Create a contribution score based on pedagogical value.

Example:

```text
File A: 45%
File B: 30%
File C: 15%
File D: 10%
```

Then sample proportionally.

## Even Better: Cross-Document Concept Connections

Example:

```text
File A: TCP
File B: Packet Loss
File C: Video Streaming
```

Graph Path:

```text
TCP
→ Packet Loss
→ Video Streaming
```

This creates a strong candidate for a hard question.

---

# Recommended Final Design

## GraphRAG

```text
Entity Importance Score
=
Centrality
+
Cross-Document Presence
+
Frequency
+
LLM Educational Importance
```

Workflow:
1. Rank entities.
2. Select Top-N.
3. Apply diversity filtering.
4. Use as quiz seeds.

## Naive RAG

```text
Chunk Importance Score
=
Concept Density
+
Explanatory Density
+
Cross-Document Relevance
-
Noise Penalty
+
LLM Educational Importance
```

Workflow:
1. Rank chunks.
2. Select Top-N.
3. Apply diversity filtering.
4. Use as quiz seeds.

---

# Summary

Primary objectives:

## 1. Meaningful Seeds
Prioritize:
- foundational concepts
- prerequisite knowledge
- high-centrality concepts
- educationally important material

Avoid:
- tables
- captions
- metadata
- trivial facts

## 2. Diversity
Ensure selected seeds:
- cover different concepts
- cover different semantic regions
- avoid near-duplicates

## 3. Cross-Document Contribution
Encourage:
- concepts appearing across multiple files
- relationships connecting multiple documents
- pedagogically important multi-document reasoning paths

Avoid forcing equal contribution from every file.

Contribution should be driven by educational importance, not document count.
