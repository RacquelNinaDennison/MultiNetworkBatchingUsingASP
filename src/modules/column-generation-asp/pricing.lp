% ============================================================
% PRICING SUBPROBLEM (Clingcon)
%
% Generates ONE candidate packing for a given transport resource
% that maximises the total shadow-price value of its contents.
%
% This mirrors thesis equation 39 — the pricing problem that
% finds the packing with the most negative reduced cost:
%
%   reduced_cost(B) = tripCost  −  Σ_p α^B_p × π_p
%
% Since tripCost is constant for a given route, minimising
% reduced cost is equivalent to maximising  Σ α^B_p × π_p,
% which is what we encode below.
%
% Decision Variables:
%   pack(Part) ∈ {0..maxItems}
%       How many units of Part go into this packing
%
% Input (instance data):
%   part(P).
%   partSize(P, Size).
%   transportCapacity(TR, Cap).
%
% Input (from Python):
%   targetTR(TR).                — which TR to build a packing for
%   shadowPrice(Part, Pi).       — π_p from master analysis
%
% Input (from Python — nogoods for excluded packings):
%   differ_K_P :- &sum{ pack(P) } >= Q+1.
%   differ_K_P :- &sum{ pack(P) } <= Q-1.
%   :- not differ_K_p1, not differ_K_p2, ...
%
% Output:
%   pack(Part) for each part via &show
% ============================================================

#const maxItems = 20.

% ============================================================
% PACKING VARIABLES
% ============================================================

&dom{0..maxItems} = pack(Part) :- part(Part).

% ============================================================
% CAPACITY CONSTRAINT  [Thesis equation 40]
%
%   Σ_p  size(p) × pack(p)  ≤  capacity(TR)
% ============================================================

&sum{ pack(Part) * Size : part(Part), partSize(Part, Size) } <= Cap :-
    targetTR(TR),
    transportCapacity(TR, Cap).

% ============================================================
% NON-TRIVIALITY
%
% A packing must contain at least one item.
% ============================================================

&sum{ pack(Part) : part(Part) } >= 1.

% ============================================================
% PRICING OBJECTIVE
%
% Maximise the total shadow-price value of the packing contents.
%
%   max  Σ_p  pack(p) × π_p
%
% A packing that achieves high value relative to tripCost will
% have negative reduced cost and should be added to the pool.
% ============================================================

&maximize{ pack(Part) * Pi : part(Part), shadowPrice(Part, Pi), Pi > 0 }.

% ============================================================
% NOGOOD INJECTION POINT
%
% Python appends rules here to exclude previously generated
% packings.  The pattern for excluding packing #K where
% pack(p1)=Q1, pack(p2)=Q2, ... is:
%
%   differ_K_p1 :- &sum{ pack(p1) } >= Q1+1.
%   differ_K_p1 :- &sum{ pack(p1) } <= Q1-1.   (omit if Q1=0)
%   differ_K_p2 :- &sum{ pack(p2) } >= Q2+1.
%   differ_K_p2 :- &sum{ pack(p2) } <= Q2-1.   (omit if Q2=0)
%   ...
%   :- not differ_K_p1, not differ_K_p2, ...
%
% This forces at least one part quantity to differ from the
% excluded packing.
% ============================================================

% ============================================================
% OUTPUT
% ============================================================

&show{ pack(Part) : part(Part) }.
