% Stage 1 ε-Constraint Encoding for Pareto Front
%
% Fix the maximum number of underDiversified (arc, part) pairs to ε,
% then minimise transport cost. Each value of ε gives one Pareto point.
%
% Usage: -c epsilon=3  (allow at most 3 underDiversified arcs)
%
% The #minimize in stage1_flow.lp handles cost minimisation.
% This file adds the hard constraint on diversification.

#const epsilon = 0.

% Transport resource balance detection
arcHasLoad(F, T, TR, P) :-
    &sum { load(F, T, TR, P) } > 0,
    possibleFlow(F, T, TR, P).

transportResourcesAvailable(F, T, P, N) :-
    activeFlow(F, T, _, P),
    N = #count { TR : possibleFlow(F, T, TR, P) }.

transportResourcesUsed(F, T, P, N) :-
    activeFlow(F, T, _, P),
    N = #count { TR : arcHasLoad(F, T, TR, P) }.

underDiversified(F, T, P) :-
    transportResourcesUsed(F, T, P, U),
    transportResourcesAvailable(F, T, P, A),
    A > 1, U < A.

% Hard constraint: at most epsilon underDiversified arcs
:- #count { F,T,P : underDiversified(F, T, P) } > epsilon.

#show underDiversified/3.
