def make_square(img, target_size):
    import numpy as np
    old_size = img.shape[:2]
    desired_size = max(old_size)
    desired_size = max(desired_size, target_size)

    delta_w = desired_size - old_size[1]
    delta_h = desired_size - old_size[0]
    top, bottom = delta_h // 2, delta_h - (delta_h // 2)
    left, right = delta_w // 2, delta_w - (delta_w // 2)

    color = [255, 255, 255]
    new_im = np.pad(img, ((top, bottom), (left, right), (0, 0)),
                    mode='constant', constant_values=255)
    return new_im


def smart_resize(img, size):
    import numpy as np
    from PIL import Image
    h, w = img.shape[:2]
    if h == size and w == size:
        return img
    pil_img = Image.fromarray(img)
    if h > size:
        pil_img = pil_img.resize((size, size), Image.LANCZOS)
    else:
        pil_img = pil_img.resize((size, size), Image.BICUBIC)
    return np.array(pil_img)
