def mean(xs):
    if not xs:
        raise ValueError("mean of an empty sequence")
    return sum(xs) / len(xs)
