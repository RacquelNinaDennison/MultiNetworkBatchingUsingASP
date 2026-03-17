% obj_baseline.lp — E1: Transport cost only (baseline).
% Minimises cost * frequency per active route.

#minimize{ C*Freq, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C) }.
