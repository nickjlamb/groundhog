from scoring.consistency import pass_hat_k


def test_pass_hat_k_three_of_five_k2():
    assert pass_hat_k(n=5, c=3, k=2) == 0.3
