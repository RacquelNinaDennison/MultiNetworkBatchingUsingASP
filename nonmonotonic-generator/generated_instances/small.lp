% Multibatching benchmark instance
% Source: instances.lp
% seed=42  harbors=1  prodlocs=2  hubs=1  parts=2  min_trs=2  disruptions=0

% ---- locations ----
location(harbor0).
location(prodloc0).
location(prodloc1).

% ---- transport resources ----
transportCapacity(tr0,1800).
transportCO2(tr0,1680).
transportCost(tr0,26).
transportSpeed(tr0,12).
transportCapacity(tr1,65).
transportCO2(tr1,90).
transportCost(tr1,1).
transportSpeed(tr1,35).
transportCapacity(tr10,1).
transportCO2(tr10,700).
transportCost(tr10,4).
transportSpeed(tr10,40).
transportCapacity(tr11,65).
transportCO2(tr11,62).
transportCost(tr11,1).
transportSpeed(tr11,25).
transportCapacity(tr12,65).
transportCO2(tr12,709).
transportCost(tr12,3).
transportSpeed(tr12,55).
transportCapacity(tr13,68).
transportCO2(tr13,160).
transportCost(tr13,6).
transportSpeed(tr13,25).
transportCapacity(tr14,146).
transportCO2(tr14,780).
transportCost(tr14,4).
transportSpeed(tr14,50).
transportCapacity(tr15,2217).
transportCO2(tr15,49470).
transportCost(tr15,32).
transportSpeed(tr15,625).
transportCapacity(tr2,96).
transportCO2(tr2,709).
transportCost(tr2,3).
transportSpeed(tr2,55).
transportCapacity(tr3,1).
transportCO2(tr3,6250).
transportCost(tr3,108).
transportSpeed(tr3,25).
transportCapacity(tr4,148).
transportCO2(tr4,780).
transportCost(tr4,4).
transportSpeed(tr4,50).
transportCapacity(tr5,65).
transportCO2(tr5,780).
transportCost(tr5,3).
transportSpeed(tr5,50).
transportCapacity(tr6,1).
transportCO2(tr6,100).
transportCost(tr6,40).
transportSpeed(tr6,25).
transportCapacity(tr7,1).
transportCO2(tr7,18000).
transportCost(tr7,278).
transportSpeed(tr7,10).
transportCapacity(tr8,1).
transportCO2(tr8,14400).
transportCost(tr8,107).
transportSpeed(tr8,25).
transportCapacity(tr9,65).
transportCO2(tr9,708).
transportCost(tr9,2).
transportSpeed(tr9,60).

% ---- parts ----
part(part1).
partSize(part1,1).
partVal(part1,5456).
valid_transport(part1,tr0).
valid_transport(part1,tr2).
valid_transport(part1,tr15).
valid_transport(part1,tr9).
valid_transport(part1,tr12).
valid_transport(part1,tr13).
valid_transport(part1,tr11).
part(part15).
partSize(part15,4).
partVal(part15,2260).
valid_transport(part15,tr0).
valid_transport(part15,tr2).
valid_transport(part15,tr15).
valid_transport(part15,tr9).
valid_transport(part15,tr12).
valid_transport(part15,tr13).
valid_transport(part15,tr11).

% ---- demand ----
demandOffer(part1,prodloc0,-20).
demandOffer(part1,prodloc1,20).
demandOffer(part15,prodloc0,-27).
demandOffer(part15,prodloc1,27).

% ---- network (ASP-generated) ----
hub(prodloc1).
route(harbor0,prodloc0,tr0,978,25428).
route(harbor0,prodloc0,tr11,978,978).
route(harbor0,prodloc1,tr0,3072,79872).
route(harbor0,prodloc1,tr11,3072,3072).
route(prodloc0,harbor0,tr0,7166,186316).
route(prodloc0,harbor0,tr9,7166,14332).
route(prodloc0,prodloc1,tr0,7625,198250).
route(prodloc0,prodloc1,tr11,7625,7625).
route(prodloc1,harbor0,tr0,16561,430586).
route(prodloc1,harbor0,tr11,16561,16561).
