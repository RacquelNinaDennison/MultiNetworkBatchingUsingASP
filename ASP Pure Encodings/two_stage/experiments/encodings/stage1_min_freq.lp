% Stage 1: Minimum Frequency Constraint
%
% Forces every active arc to have at least 2 trips. This guarantees
% Stage 2 has room to diversify — no arc carries 100% of a part on
% a single trip.
%
% Without this, R_1 = 0 on any arc with freq=1.
% With this, the theoretical maximum R_1 >= 0.5 on every arc.

:- routeFreq(F, T, TR, 1, _).
