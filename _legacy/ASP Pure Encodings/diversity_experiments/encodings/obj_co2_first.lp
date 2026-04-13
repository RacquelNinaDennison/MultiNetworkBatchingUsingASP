% obj_co2_first.lp — E5: CO2 emissions prioritised first.
% Lexicographic: CO2 @3, cost @2, holding @1.
% Tests: what happens when we optimise for emissions above all else?

#minimize{ D*Freq*E @3, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, D, _),
    transportCO2(TR,E) }.

#minimize{ C*Freq @2, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C) }.

#minimize{ D*V*Freq @1, From,To,TR,P :
    activeFlow(From,To,TR,P),
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, D, _),
    partVal(P,V) }.
