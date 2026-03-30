% Soft Constraint @1: Dispatch Cost
%
% Each used trip incurs the route's per-trip dispatch cost. This gives
% the solver an incentive to consolidate into fewer trips — but at @1,
% it is secondary to the resilience objectives at @2 and @3.
%
% Input: routeCost(From, To, TR, C) — per-trip cost (passed from bridge)

usedTrip(F, T, TR, K) :- tripHasPart(F, T, TR, K, _).

:~ usedTrip(F, T, TR, K), routeCost(F, T, TR, C).
   [C@1, F, T, TR, K]

#show usedTrip/4.
