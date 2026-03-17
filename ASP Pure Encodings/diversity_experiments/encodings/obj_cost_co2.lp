% obj_cost_co2.lp — E2: Transport cost + CO2 emissions.
% Transport cost optimised first (@2), then CO2 (@1).

#minimize{ C*Freq @2, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C) }.

#minimize{ D*Freq*E @1, From,To,TR :
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, D, _),
    transportCO2(TR,E) }.
