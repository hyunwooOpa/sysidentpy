""" Build Polynomial NARMAX Models using the Entropic Regression algorithm """

# Authors:
#           Wilson Rocha Lacerda Junior <wilsonrljr@outlook.com>
# License: BSD 3 clause

import numpy as np
from numpy import linalg as LA
from scipy.spatial.distance import cdist
from scipy.special import psi

from ..narmax_base import (
    GenerateRegressors,
    HouseHolder,
    InformationMatrix,
    ModelInformation,
    ModelPrediction,
)
from ..parameter_estimation.estimators import Estimators
from ..utils._check_arrays import (
    _check_positive_int,
    _num_features,
    check_X_y,
    check_random_state,
)


class ER(
    Estimators,
    GenerateRegressors,
    HouseHolder,
    ModelInformation,
    InformationMatrix,
    ModelPrediction,
):
    """Entropic Regression Algorithm

    Build Polynomial NARMAX model using the Entropic Regression Algorithm ([1]_).
    This algorithm is based on the Matlab package available on:
    https://github.com/almomaa/ERFit-Package

    The NARMAX model is described as:

    .. math::

        y_k= F^\ell[y_{k-1}, \dotsc, y_{k-n_y},x_{k-d}, x_{k-d-1}, \dotsc, x_{k-d-n_x} + e_{k-1}, \dotsc, e_{k-n_e}] + e_k

    where :math:`n_y\in \mathbb{N}^*`, :math:`n_x \in \mathbb{N}`, :math:`n_e \in \mathbb{N}`,
    are the maximum lags for the system output and input respectively;
    :math:`x_k \in \mathbb{R}^{n_x}` is the system input and :math:`y_k \in \mathbb{R}^{n_y}`
    is the system output at discrete time :math:`k \in \mathbb{N}^n`;
    :math:`e_k \in \mathbb{R}^{n_e}` stands for uncertainties and possible noise
    at discrete time :math:`k`. In this case, :math:`\mathcal{F}^\ell` is some nonlinear function
    of the input and output regressors with nonlinearity degree :math:`\ell \in \mathbb{N}`
    and :math:`d` is a time delay typically set to :math:`d=1`.

    Parameters
    ----------
    ylag : int, default=2
        The maximum lag of the output.
    xlag : int, default=2
        The maximum lag of the input.
    k : int, default=2
        The kth nearest neighbor to be used in estimation.
    q : float, default=0.99
        Quantile to compute, which must be between 0 and 1 inclusive.
    p : default=inf,
        Lp Measure of the distance in Knn estimator.
    n_perm: int, default=200
        Number of permutation to be used in shuffle test
    estimator : str, default="least_squares"
        The parameter estimation method.
    skip_forward = bool, default=False
        To be used for difficult and highly uncertain problems.
        Skipping the forward selection results in more accurate solution,
        but comes with higher computational cost.
    lam : float, default=0.98
        Forgetting factor of the Recursive Least Squares method.
    delta : float, default=0.01
        Normalization factor of the P matrix.
    offset_covariance : float, default=0.2
        The offset covariance factor of the affine least mean squares
        filter.
    mu : float, default=0.01
        The convergence coefficient (learning rate) of the filter.
    eps : float
        Normalization factor of the normalized filters.
    gama : float, default=0.2
        The leakage factor of the Leaky LMS method.
    weight : float, default=0.02
        Weight factor to control the proportions of the error norms
        and offers an extra degree of freedom within the adaptation
        of the LMS mixed norm method.
    model_type: str, default="NARMAX"
        The user can choose "NARMAX", "NAR" and "NFIR" models

    Examples
    --------
    >>> import numpy as np
    >>> import matplotlib.pyplot as plt
    >>> from sysidentpy.model_structure_selection import ER
    >>> from sysidentpy.basis_function._basis_function import Polynomial
    >>> from sysidentpy.utils.display_results import results
    >>> from sysidentpy.metrics import root_relative_squared_error
    >>> from sysidentpy.utils.generate_data import get_miso_data, get_siso_data
    >>> x_train, x_valid, y_train, y_valid = get_siso_data(n=1000,
    ...                                                    colored_noise=True,
    ...                                                    sigma=0.2,
    ...                                                    train_percentage=90)
    >>> basis_function = Polynomial(degree=2)
    >>> model = ER(basis_function=basis_function,
    ...              ylag=2, xlag=2
    ...              )
    >>> model.fit(x_train, y_train)
    >>> yhat = model.predict(x_valid, y_valid)
    >>> rrse = root_relative_squared_error(y_valid, yhat)
    >>> print(rrse)
    0.001993603325328823
    >>> r = pd.DataFrame(
    ...     results(
    ...         model.final_model, model.theta, model.err,
    ...         model.n_terms, err_precision=8, dtype='sci'
    ...         ),
    ...     columns=['Regressors', 'Parameters', 'ERR'])
    >>> print(r)
        Regressors Parameters         ERR
    0        x1(k-2)     0.9000       0.0
    1         y(k-1)     0.1999       0.0
    2  x1(k-1)y(k-1)     0.1000       0.0

    References
    ----------
    .. [1] Abd AlRahman R. AlMomani, Jie Sun, and Erik Bollt. How Entropic
        Regression Beats the Outliers Problem in Nonlinear System
        Identification. Chaos 30, 013107 (2020).
    .. [2] Alexander Kraskov, Harald St¨ogbauer, and Peter Grassberger.
        Estimating mutual information. Physical Review E, 69:066-138,2004
    .. [3] Alexander Kraskov, Harald St¨ogbauer, and Peter Grassberger.
        Estimating mutual information. Physical Review E, 69:066-138,2004
    .. [4] Alexander Kraskov, Harald St¨ogbauer, and Peter Grassberger.
        Estimating mutual information. Physical Review E, 69:066-138,2004
    """

    def __init__(
        self,
        *,
        ylag=2,
        xlag=2,
        q=0.99,
        estimator="least_squares",
        extended_least_squares=False,
        h=0.01,
        k=2,
        mutual_information_estimator="mutual_information_knn",
        n_perm=200,
        p=np.inf,
        skip_forward=False,
        lam=0.98,
        delta=0.01,
        offset_covariance=0.2,
        mu=0.01,
        eps=np.finfo(np.float64).eps,
        gama=0.2,
        weight=0.02,
        model_type="NARMAX",
        basis_function=None,
        random_state=None,
    ):
        self.basis_function = basis_function
        self.model_type = model_type
        self.xlag = xlag
        self.ylag = ylag
        self.non_degree = basis_function.degree
        self.max_lag = self._get_max_lag(ylag, xlag)
        self.k = k
        self.estimator = estimator
        self._extended_least_squares = extended_least_squares
        self.q = q
        self.h = h
        self.mutual_information_estimator = mutual_information_estimator
        self.n_perm = n_perm
        self.p = p
        self.skip_forward = skip_forward
        self.random_state = random_state
        self.rng = check_random_state(random_state)
        self._validate_params()
        super().__init__(
            lam=lam,
            delta=delta,
            offset_covariance=offset_covariance,
            mu=mu,
            eps=eps,
            gama=gama,
            weight=weight,
        )

    def _validate_params(self):
        """Validate input params."""
        if isinstance(self.ylag, int) and self.ylag < 1:
            raise ValueError("ylag must be integer and > zero. Got %f" % self.ylag)

        if isinstance(self.xlag, int) and self.xlag < 1:
            raise ValueError("xlag must be integer and > zero. Got %f" % self.xlag)

        if not isinstance(self.xlag, (int, list)):
            raise ValueError("xlag must be integer and > zero. Got %f" % self.xlag)

        if not isinstance(self.ylag, (int, list)):
            raise ValueError("ylag must be integer and > zero. Got %f" % self.ylag)

        if not isinstance(self.k, int) or self.k < 1:
            raise ValueError("k must be integer and > zero. Got %f" % self.k)

        if not isinstance(self.n_perm, int) or self.n_perm < 1:
            raise ValueError("n_perm must be integer and > zero. Got %f" % self.n_perm)

        if not isinstance(self.q, float) or self.q > 1 or self.q <= 0:
            raise ValueError(
                "q must be float and must be between 0 and 1 inclusive. Got %f" % self.q
            )

        if not isinstance(self.skip_forward, bool):
            raise TypeError(
                "skip_forward must be False or True. Got %f" % self.skip_forward
            )

        if not isinstance(self._extended_least_squares, bool):
            raise TypeError(
                "extended_least_squares must be False or True. Got %f"
                % self._extended_least_squares
            )

        if self.model_type not in ["NARMAX", "NAR", "NFIR"]:
            raise ValueError(
                "model_type must be NARMAX, NAR or NFIR. Got %s" % self.model_type
            )

    def mutual_information_knn(self, y, y_perm):
        """Finds the mutual information.
        Finds the mutual information between :math:`x` and :math:`y` given :math:`z`.

        This code is based on Matlab Entropic Regression package.

        Parameters
        ----------
        y : ndarray of floats
            The source signal.
        y_perm : ndarray of floats
            The destination signal.

        Returns
        -------
        ksg_estimation : float
            The conditioned mutual information.

        References
        ----------
        .. [1] Abd AlRahman R. AlMomani, Jie Sun, and Erik Bollt. How Entropic
            Regression Beats the Outliers Problem in Nonlinear System
            Identification. Chaos 30, 013107 (2020).
        .. [2] Alexander Kraskov, Harald St¨ogbauer, and Peter Grassberger.
            Estimating mutual information. Physical Review E, 69:066-138,2004
        .. [3] Alexander Kraskov, Harald St¨ogbauer, and Peter Grassberger.
            Estimating mutual information. Physical Review E, 69:066-138,2004
        .. [4] Alexander Kraskov, Harald St¨ogbauer, and Peter Grassberger.
            Estimating mutual information. Physical Review E, 69:066-138,2004
        """
        joint_space = np.concatenate([y, y_perm], axis=1)
        smallest_distance = np.sort(
            cdist(joint_space, joint_space, "minkowski", p=self.p).T
        )
        idx = np.argpartition(smallest_distance[-1, :], self.k + 1)[: self.k + 1]
        smallest_distance = smallest_distance[:, idx]
        epsilon = smallest_distance[:, -1].reshape(-1, 1)
        smallest_distance_y = cdist(y, y, "minkowski", p=self.p)
        less_than_array_nx = np.array((smallest_distance_y < epsilon)).astype(int)
        nx = (np.sum(less_than_array_nx, axis=1) - 1).reshape(-1, 1)
        smallest_distance_y_perm = cdist(y_perm, y_perm, "minkowski", p=self.p)
        less_than_array_ny = np.array((smallest_distance_y_perm < epsilon)).astype(int)
        ny = (np.sum(less_than_array_ny, axis=1) - 1).reshape(-1, 1)
        arr = psi(nx + 1) + psi(ny + 1)
        ksg_estimation = (
            psi(self.k) + psi(y.shape[0]) - np.nanmean(arr[np.isfinite(arr)])
        )
        return ksg_estimation