% =============================================================================
% Toy Instance: 3 locations, 1 product, linear chain l1 → l2 → l3
% Product p1 is produced at l1 (rate 6) and consumed at l3 (rate 6).
% Transport resources: tr1 (capacity 10, cost 56) and tr2 (capacity 15, cost 42)
%
% OPTIMAL SOLUTION (verified):
%   tr2 is better: higher capacity (15 > 10) AND cheaper (42 < 56).
%   Pack 3×p1 (size 12 ≤ 15) at frequency 2 (3×2=6).
%
%   flow(l1,l2,p1,6).  flow(l2,l3,p1,6).
%   pack(3,p1,0,l1,l2,tr2). freq(0,l1,l2,tr2,2). → 3×2=6 ✓  cost: 2×1×42 =  84
%   pack(3,p1,0,l2,l3,tr2). freq(0,l2,l3,tr2,2). → 3×2=6 ✓  cost: 2×2×42 = 168
%   Total cost: 252
%
% For comparison, the tr1-only solution costs:
%   pack(2,p1,...,tr1) freq 3 → 3×1×56 + 3×2×56 = 168+336 = 504  (worse)
% =============================================================================

% Locations
location(l1). location(l2). location(l3).

% Products
part(p1).
partSize(p1, 4).
partValue(p1, 1000).

% Supply and demand (positive = production, negative = consumption)
demandOffer(p1, l1, 6).
demandOffer(p1, l3, -6).

% Transport resources
transportCapacity(tr1, 10).
transportCapacity(tr2, 15).

% Routes: route(From, To, TransportResource, Distance, CostPerDistance)
% Link l1 → l2: distance 1
route(l1, l2, tr1, 1, 56).
route(l1, l2, tr2, 1, 42).

% Link l2 → l3: distance 2
route(l2, l3, tr1, 2, 56).
route(l2, l3, tr2, 2, 42).

% CO2 data (optional, for extended cost model)
co2emission(tr1, 60).
co2emission(tr2, 45).
co2price(90).
