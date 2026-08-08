# Technical speech patterns

For a technical point, explain: plain definition; exact input; operation or decision; output and downstream use; small example; practical benefit and limitation.

## RNN

Do not say only that a recurrent neural network uses sequence and history. In an iterative optimizer, step 12 can receive the current search state while the recurrent state summarizes decisions from steps 1–11. Explain which next branching or selection decision uses that memory. Mention compressed distant events and sequential computation as limitations when relevant.

## Attention

Do not say only that attention handles a variable number of candidates. A solver might have 37 candidate cuts in one iteration and 112 in the next. Attention can score each candidate relative to current solver state and emphasize relevant ones without fixing pool size. Attention is a mechanism, not automatically a Transformer.

## MILP bipartite graph

For mixed-integer linear programming, put variables on one side and constraints on the other. Connect a variable to a constraint when it appears, using its coefficient as an edge feature. This preserves sparse variable–constraint structure and permutation invariance. Different formulations of the same problem can produce different graphs, and a static graph can omit global solver dynamics.

## Cut selection or SDP

Expand cutting-plane selection and semidefinite programming on first spoken use. Then narrate candidate/object generation, observed state/features, scoring or optimization, the selected/updated object, and its effect on the next solver iteration or result.

## Practical meaning

End with a paper-specific sentence: “Practically, this matters because it changes ___ under the constraint ___, at the cost or risk of ___.”
