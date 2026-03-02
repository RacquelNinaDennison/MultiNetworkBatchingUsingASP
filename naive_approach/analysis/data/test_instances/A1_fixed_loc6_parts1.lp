% =========================================
% A1_FIXED_LOC_6_PARTS_1
% 6 locations, 1 product, 2 transport resources
% =========================================

#const maxFlow = 14.
#const maxFreq = 6.
#const maxParts = 5.
#const maxBins = 1.

numFlow(0..maxFlow).
numFreq(0..maxFreq).
numParts(0..maxParts).
bins(0..maxBins).

location(l1). location(l2). location(l3). location(l4). location(l5). location(l6).

part(p1).
partSize(p1, 2).

transportCapacity(tr1, 8).
transportCapacity(tr2, 12).

co2price(90).
co2emission(tr1, 30).
co2emission(tr2, 50).

demandOffer(p1, l1, 12).
demandOffer(p1, l5, -5).
demandOffer(p1, l6, -7).

route(l1,l3,tr1,2,10).
route(l1,l3,tr2,2,14).
route(l2,l3,tr1,2,10).
route(l2,l4,tr2,3,12).
route(l1,l4,tr2,4,16).
route(l3,l5,tr1,2,10).
route(l3,l5,tr2,2,14).
route(l3,l6,tr2,3,12).
route(l4,l5,tr1,2,10).
route(l4,l6,tr2,3,12).
