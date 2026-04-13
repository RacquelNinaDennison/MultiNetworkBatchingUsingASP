_transCost(From,To,TR, C*Freq) :-
    routeFreq(From,To,TR,Freq,_), route(From,To,TR,_,C).

#minimize { V,F,T,TR : _transCost(F,T,TR,V) }.