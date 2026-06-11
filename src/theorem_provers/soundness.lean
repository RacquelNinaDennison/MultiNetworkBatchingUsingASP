-- One bin's data on a fixed arc, for a fixed part:
-- quantity packed (your α / pack's N) and dispatch frequency (your λ / freq's F).

structure Part where
part_size : Nat
part_value: Nat
part_name : String

structure TransportResource where
  res_name : String
  res_cap  : Nat

structure BinData where
  qty  : Nat
  freq : Nat
  transport : TransportResource
  part : Part

-- The decoded picture on one arc for one part: the bins, and the flow assigned.
structure ArcPart where
  bins : List BinData
  flow : Nat



def dispatched(ap:ArcPart) : Nat :=
    (ap.bins.map (fun b => b.qty * b.freq)).sum

-- The specification: dispatched parts must meet the required flow.
-- This is  Σ λ_B · α_{p,B}  ≥  flow,  written flow ≤ dispatched.
def DispatchOK (ap : ArcPart) : Prop :=
  ap.flow ≤ dispatched ap



theorem dispatch_mono (b : BinData) (bs : List BinData) (f: Nat) :
  dispatched (ArcPart.mk [b] f) ≤ dispatched (ArcPart.mk (b :: bs) f) :=
  by
  simp[dispatched]
