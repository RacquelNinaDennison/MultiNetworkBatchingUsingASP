% obj_full.lp — E3: Transport cost + CO2 + Holding cost proxy.
% Lexicographic: cost @3, CO2 @2, holding @1.

#minimize{ C*Freq @3, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C) }.

#minimize{ D*Freq*E @2, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, D, _),
    transportCO2(TR,E) }.

#minimize{ D*V*Freq @1, From,To,TR,P :
    activeFlow(From,To,TR,P),
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, D, _),
    partVal(P,V) }.
