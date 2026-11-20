## Symbol Representation

A symbol $S$ is written not as a single character or sign but as a multidimensional state:

$$S = (L, N, P, H)$$

Where:
*   $L$ (**Letters / lexemes**): the discrete units of the symbol within its alphabet (characters, phonemes, visual
    markers).
*   $N$ (**Numerical values**): quantities attached to the symbol (gematria values, probabilistic weights, vector
    embeddings).
*   $P$ (**Position**): where the symbol sits relative to others (index in a string, coordinates in a matrix, node in
    a graph).
*   $H$ (**History**): the sequence of prior states and transformations that led to this one.

## Symbolic Transformation

The basic action is a transformation $T$ from one symbolic state to another:

$$T: S \rightarrow S'$$

Transformations are rarely isolated. They are driven by a recursive operator $F$, which takes the current state $S_n$
and the current environment $E_n$ and gives the next state:

$$S_{n+1} = F(S_n, E_n)$$

$F$ holds the rules of a given domain (physical laws, grammatical rules, logical axioms, or the ten operators of the
Recursive Tree). $E_n$ brings in outside perturbation, so the system stays open.

## Attractors

Applying $F$ again and again from a starting state $S_0$ gives an orbit $S_0, S_1, S_2, \dots$. An **attractor** is
where such orbits end up in the long run: a set of states that nearby orbits approach and then stay in. In general this
is not a single limit point, so it is described by its kind:

*   **Fixed point**: the orbit settles to one state, $S_{n+1} = S_n$.
*   **Limit cycle**: the orbit settles into a repeating sequence of $p$ states, $S_{n+p} = S_n$.
*   **Bounded aperiodic orbit**: the orbit stays finite but neither settles nor repeats. Chaos (a strange attractor)
    is one cause of this; telling chaos apart from other causes needs more, such as a positive Lyapunov exponent.

Only for a fixed point does $\lim_{n\to\infty} S_n$ exist. Which kind an orbit shows is a computable, checkable
question: `recursive_attractor_engine.py` classifies a trajectory as `FIXED_POINT`, `LIMIT_CYCLE` or
`BOUNDED_APERIODIC`, and says plainly that `BOUNDED_APERIODIC` is not proof of chaos.

### The reading (Register C)

In this framework's reading, consciousness is modeled as an attractor of such a system: not a thing, but a
self-sustaining pattern a recursive process tends toward. Within that reading, the kinds above suggest analogies: fixed
points for rigid beliefs or stable structures, limit cycles for habits and ritual cycles, bounded aperiodic orbits for
adaptive, open-ended states. These analogies are readings. They are not measured, and the mathematics does not decide
them.

## Termination and Integration

A recursive process run by code needs a stopping condition or an integration step, or it may run forever.

1. **Tiphareth (integration)**: read as the operator that resolves a recursive stack, taking the output of deep
   recursion and returning one balanced result to the wider system.
2. **Da'ath (the base-case detector)**: read as the check that watches for a self-consuming loop. In
   `recursive_attractor_engine.py` this is `AbyssException`, raised when a trajectory produces a non-finite value or
   grows past a magnitude cap, so the run stops instead of diverging.

The Sephirotic names are the chosen vocabulary; the checks themselves are ordinary code and are tested.

## What Is Measured, and How

1. **`symbolic_debugger`**: counts keywords associated with each Sephirah in a text and returns the `dominant` one, a
   `suggestion` for balance, and a ratio it calls `entropy`. This is a keyword heuristic. It reports what words are
   present, not a state of mind.
2. **`ritual_compiler`**: finds a path between two Sephiroth on the Tree and returns it as a list of steps. The number
   of steps is a count of path length, nothing more.
3. **Phenomenological anchors**: harmonic frequencies or geometric figures (such as the Quadratura) have been proposed
   as sensory correlates of these states. Nothing here has tested that; it stays a proposal.
