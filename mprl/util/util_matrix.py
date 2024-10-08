"""
    Utilities of matrix operation
"""
from typing import Iterable
from typing import Optional
from typing import Union
from typing import Tuple
import numpy as np
import torch


def build_lower_matrix(param_diag: torch.Tensor,
                       param_off_diag: Optional[torch.Tensor]) -> torch.Tensor:
    """
    Compose the lower triangular matrix L from diag and off-diag elements
    It seems like faster than using the cholesky transformation from PyTorch
    Args:
        param_diag: diagonal parameters
        param_off_diag: off-diagonal parameters

    Returns:
        Lower triangular matrix L

    """
    dim_pred = param_diag.shape[-1]
    # Fill diagonal terms
    L = param_diag.diag_embed()
    if param_off_diag is not None:
        # Fill off-diagonal terms
        [row, col] = torch.tril_indices(dim_pred, dim_pred, -1)
        L[..., row, col] = param_off_diag[..., :]

    return L


def reverse_build_matrix(L: torch.Tensor, has_off_diag: bool) -> \
        Tuple[torch.Tensor, Union[torch.Tensor, None]]:
    """
    Decompose the lower triangular matrix L to diag and off-diag elements
    Args:
        L: Lower triangular matrix L
        has_off_diag: whether the matrix has off-diagonal elements

    Returns:
        param_diag, None: if has_off_diag is False
        param_diag, param_off_diag: otherwise

    """
    param_diag = torch.diagonal(L, dim1=-2, dim2=-1)
    if has_off_diag:
        [row, col] = torch.tril_indices(L.shape[-1], L.shape[-1], -1)
        param_off_diag = L[..., row, col]
        return param_diag, param_off_diag
    else:
        return param_diag, None


def transform_to_cholesky(mat: torch.Tensor) -> torch.Tensor:
    """
    Transform an unconstrained matrix to cholesky, will abandon half of the data
    Args:
        mat: an unconstrained square matrix

    Returns:
        lower triangle matrix as Cholesky
    """
    lct = torch.distributions.transforms.LowerCholeskyTransform(cache_size=0)
    return lct(mat)


def add_expand_dim(data: Union[torch.Tensor, np.ndarray],
                   add_dim_indices: [int],
                   add_dim_sizes: [int]) -> Union[torch.Tensor, np.ndarray]:
    """
    Add additional dimensions to tensor and expand accordingly
    Args:
        data: tensor to be operated. Torch.Tensor or numpy.ndarray
        add_dim_indices: the indices of added dimensions in the result tensor
        add_dim_sizes: the expanding size of the additional dimensions

    Returns:
        result: result tensor after adding and expanding
    """
    num_data_dim = data.ndim
    num_dim_to_add = len(add_dim_indices)

    add_dim_reverse_indices = [num_data_dim + num_dim_to_add + idx
                               for idx in add_dim_indices]

    str_add_dim = ""
    str_expand = ""
    add_dim_index = 0
    for dim in range(num_data_dim + num_dim_to_add):
        if dim in add_dim_indices or dim in add_dim_reverse_indices:
            str_add_dim += "None, "
            str_expand += str(add_dim_sizes[add_dim_index]) + ", "
            add_dim_index += 1
        else:
            str_add_dim += ":, "
            if type(data) == torch.Tensor or type(data) == torch.nn.Parameter:
                str_expand += "-1, "
            elif type(data) == np.ndarray:
                str_expand += "1, "
            else:
                raise NotImplementedError

    str_add_dime_eval = "data[" + str_add_dim + "]"
    if type(data) == torch.Tensor or type(data) == torch.nn.Parameter:
        return eval("eval(str_add_dime_eval).expand(" + str_expand + ")")
    else:
        return eval("np.tile(eval(str_add_dime_eval),[" + str_expand + "])")


def to_cholesky(diag_vector=None, off_diag_vector=None,
                L=None, cov_matrix=None):
    """
    Compute Cholesky matrix
    Args:
        diag_vector: diag elements in a vector
        off_diag_vector: off-diagonal elements in a vector
        L: Cholesky matrix
        cov_matrix: Covariance matrix

    Returns:
        Cholesky matrix L
    """
    if L is not None:
        pass
    elif cov_matrix is None:
        assert diag_vector is not None and off_diag_vector is not None
        L = build_lower_matrix(diag_vector, off_diag_vector)
    elif diag_vector is None and off_diag_vector is None:
        L = torch.linalg.cholesky(cov_matrix)
    else:
        raise RuntimeError("Unexpected behaviours")
    return L


def tensor_linspace(start: Union[float, int, torch.Tensor],
                    end: Union[float, int, torch.Tensor],
                    steps: int) -> torch.Tensor:
    """
    Vectorized version of torch.linspace.
    Modified from:
    https://github.com/zhaobozb/layout2im/blob/master/models/bilinear.py#L246

    Args:
        start: start value, scalar or tensor
        end: end value, scalar or tensor
        steps: num of steps

    Returns:
        linspace tensor
    """
    # Shape of start:
    # [*add_dim, dim_data] or a scalar
    #
    # Shape of end:
    # [*add_dim, dim_data] or a scalar
    #
    # Shape of out:
    # [*add_dim, steps, dim_data]

    # - out: Tensor of shape start.size() + (steps,), such that
    #   out.select(-1, 0) == start, out.select(-1, -1) == end,
    #   and the other elements of out linearly interpolate between
    #   start and end.

    if isinstance(start, torch.Tensor) and not isinstance(end, torch.Tensor):
        end += torch.zeros_like(start)
    elif not isinstance(start, torch.Tensor) and isinstance(end, torch.Tensor):
        start += torch.zeros_like(end)
    elif isinstance(start, torch.Tensor) and isinstance(end, torch.Tensor):
        assert start.size() == end.size()
    else:
        return torch.linspace(start, end, steps)

    view_size = start.size() + (1,)
    w_size = (1,) * start.dim() + (steps,)
    out_size = start.size() + (steps,)

    start_w = torch.linspace(1, 0, steps=steps).to(start.device)
    start_w = start_w.view(w_size).expand(out_size)
    end_w = torch.linspace(0, 1, steps=steps).to(start.device)
    end_w = end_w.view(w_size).expand(out_size)

    start = start.contiguous().view(view_size).expand(out_size)
    end = end.contiguous().view(view_size).expand(out_size)

    out = start_w * start + end_w * end
    out = torch.einsum('...ji->...ij', out)
    return out


def indexing_interpolate(data: torch.Tensor,
                         indices: torch.Tensor) -> torch.Tensor:
    """
    Indexing values from a given tensor's data, using non-integer indices and
    thus apply interpolation.

    Args:
        data: data tensor from where indexing happens
        indices: float indices tensor

    Returns:
        indexed and interpolated data
    """
    # Shape of data:
    # [num_data, *dim_data]
    #
    # Shape of indices:
    # [*add_dim, num_indices]
    #
    # Shape of interpolate_result:
    # [*add_dim, num_indices, *dim_data]

    ndim_data = data.ndim - 1
    indices_0 = torch.clip(indices.floor().long(), 0,
                           data.shape[-data.ndim] - 2)
    indices_1 = indices_0 + 1
    weights = indices - indices_0
    if ndim_data > 0:
        weights = add_expand_dim(weights,
                                 range(indices.ndim, indices.ndim + ndim_data),
                                 [-1] * ndim_data)
    interpolate_result = torch.lerp(data[indices_0], data[indices_1], weights)
    return interpolate_result


def get_sub_tensor(data: torch.Tensor, dims: Iterable, indices: Iterable):
    """
    Get sub tensor from a given tensor's data, and multi dimensional indices
    First form up an expression string and then slice the data tensor
    Args:
        data: original tensor
        dims: dimensions to be sliced
        indices: slice of these dimensions

    Returns:
        sliced tensor

    """
    exp_str = ""
    for i, dim in enumerate(dims):
        if dim < 0:
            dim += data.ndim
        temp_str = ":, " * dim
        dim_exp_str = f"[{temp_str}indices[{i}]]"
        exp_str += dim_exp_str

    return eval("data" + exp_str)