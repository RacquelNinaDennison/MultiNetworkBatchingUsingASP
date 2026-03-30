## Why ASP in this case

Using traditiona integer linear programming presenets some nuances when we want to diversify packages or the items packed within given constraints. 
However, ASP allows us to express this easily. 

## Conflicting objective functions

At the moment, the only objective function outlined within the entire network is the following: 

```
#minimize{D*Freq*E,From,To,TR: routeFreq(From, To, TR, Freq, _),
route(From, To, TR,D, _),transportCO2(TR,E);C*Freq,From,To,TR: routeFreq(From, To, TR, Freq, TotalCap),route(From, To, TR, _, C)}.

```

This objective tries to minimize the cost of the route interms of cost of transportation and the cost from CO2Emissons. Its obvious to see that when the frequency is low, the cost and co2emissions will be low, as frequency is the only parameter that we can tuned in this instance.

If we think what the solver will do, it will try and pack as many items as possible into packets in order to transport them at a low frequency but still satisfy the demand of the network. 

