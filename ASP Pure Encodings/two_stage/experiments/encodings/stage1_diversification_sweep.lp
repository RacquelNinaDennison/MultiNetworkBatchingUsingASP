% Stage 1 Diversification Sweep Encoding
%
% This encoding puts transport cost and resource balance at the SAME
% priority level (@1) so they compete. The weight of the diversification
% penalty is controlled by #const div_weight, which can be overridden
% from the command line: -c div_weight=100
%
% Sweep div_weight from 0 (pure cost) to large values (force diversification)
% to generate the cost vs R_TR Pareto front.
%
% NOTE: This file replaces the #minimize in stage1_flow.lp. When loading
% this file, stage1_flow.lp's #minimize still fires at default priority
% but @1 is higher, so these weak constraints dominate.

#const div_weight = 0.

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

% Compute unscaled cost for the sweep (stage1_flow.lp scales by /1000
% which zeroes out small-instance costs). This uses the raw route cost.
_sweepCost(From,To,TR, C*Freq) :-
    routeFreq(From,To,TR,Freq,_), route(From,To,TR,_,C).

% Both at @1 — they compete directly
:~ _sweepCost(F,T,TR,V). [V@1, trans, F, T, TR]
:~ underDiversified(F, T, P). [div_weight@1, div, F, T, P]

#show underDiversified/3.
