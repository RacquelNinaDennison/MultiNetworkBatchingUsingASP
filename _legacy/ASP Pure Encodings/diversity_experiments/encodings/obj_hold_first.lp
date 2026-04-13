% obj_hold_first.lp — E4: Holding cost prioritised first.
% Lexicographic: holding @3, cost @2, CO2 @1.
% Tests: what happens when we optimise for tied-up capital above all else?

#minimize{ D*V*Freq @3, From,To,TR,P :
    activeFlow(From,To,TR,P),
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, D, _),
    partVal(P,V) }.

#minimize{ C*Freq @2, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C) }.

#minimize{ D*Freq*E @1, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, D, _),
    transportCO2(TR,E) }.
