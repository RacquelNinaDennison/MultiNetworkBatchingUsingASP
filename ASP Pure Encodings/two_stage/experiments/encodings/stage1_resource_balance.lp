% Stage 1 Resilience: Transport Resource Balance
%
% On arcs served by multiple transport resources, penalise when a part
% flows on fewer resources than are available. This ensures that losing
% one transport resource does not eliminate all supply of a part on that arc.
%
% Metric targeted: R_TR
%
% NOTE: When this file is loaded, the #minimize in stage1_flow.lp operates
% at default priority. This constraint at @1 will be lexicographically
% dominant over cost. To make them compete, replace #minimize with an
% explicit weak constraint at the same level.

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

:~ underDiversified(F, T, P). [5@1, F, T, P]

#show underDiversified/3.
