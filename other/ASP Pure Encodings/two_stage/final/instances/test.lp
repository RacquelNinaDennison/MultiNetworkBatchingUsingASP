% % Most vulnerable arc identified by R_TR max-flow
% disrupted(l3, l4, tr1).

% % Nominal Stage 1 loads (reference for deviation)
% nominalLoad(l1, l2, tr1, p1, 3).
% nominalLoad(l1, l2, tr1, p2, 3).
% nominalLoad(l1, l3, tr1, p1, 7).
% nominalLoad(l1, l3, tr1, p2, 9).
% nominalLoad(l2, l4, tr1, p1, 3).
% nominalLoad(l2, l4, tr1, p2, 3).
% nominalLoad(l3, l4, tr1, p1, 7).
% nominalLoad(l3, l4, tr1, p2, 9).

% % Nominal Stage 1 cost
% nominalCost(560).


disrupted(l1, l3, tr2).

nominalLoad(l1, l2, tr1, p1, 1).
nominalLoad(l1, l2, tr1, p2, 12).
nominalLoad(l1, l2, tr2, p1, 3).
nominalLoad(l1, l2, tr2, p2, 8).
nominalLoad(l1, l3, tr1, p1, 3).
nominalLoad(l1, l3, tr1, p2, 4).
nominalLoad(l1, l3, tr2, p1, 3).
nominalLoad(l1, l3, tr2, p2, 16).
nominalLoad(l2, l3, tr1, p1, 7).
nominalLoad(l2, l3, tr1, p2, 4).
nominalLoad(l2, l3, tr2, p1, 7).
nominalLoad(l2, l3, tr2, p2, 6).
nominalLoad(l2, l6, tr1, p1, 10).
nominalLoad(l3, l5, tr1, p1, 4).
nominalLoad(l3, l5, tr1, p2, 8).
nominalLoad(l3, l5, tr2, p1, 6).
nominalLoad(l3, l5, tr2, p2, 12).
nominalLoad(l3, l6, tr1, p1, 5).
nominalLoad(l3, l6, tr1, p2, 1).
nominalLoad(l3, l6, tr2, p1, 5).
nominalLoad(l3, l6, tr2, p2, 9).

nominalCost(4536).
