import argparse
import os
import cv2

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw
from torchvision import transforms

from utils.data_loading import BasicDataset
from unet import UNet

def predict_img(net,
                full_img,
                device,
                scale_factor=1,
                out_threshold=0.5):
    net.eval()
    img = torch.from_numpy(BasicDataset.preprocess(full_img, scale_factor, is_mask=False))
    img = img.unsqueeze(0)
    img = img.to(device=device, dtype=torch.float32)

    with torch.no_grad():
        output = net(img)

        if net.n_classes > 1:
            probs = F.softmax(output, dim=1)[0]
        else:
            probs = torch.sigmoid(output)[0]

        tf = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((full_img.size[1], full_img.size[0])),
            transforms.ToTensor()
        ])

        full_mask = tf(probs.cpu()).squeeze()

    if net.n_classes == 1:
        return (full_mask > out_threshold).numpy()
    else:
        return F.one_hot(full_mask.argmax(dim=0), net.n_classes).permute(2, 0, 1).numpy()


def get_args():
    parser = argparse.ArgumentParser(description='Predict masks from input images')
    parser.add_argument('--model', '-m', default='checkpoints/checkpoint_epoch200.pth', metavar='FILE',
                        help='Specify the file in which the model is stored')
    parser.add_argument('--input', '-i', help='Filename of input image', default='video/3.jpg')
    parser.add_argument('--output', '-o', help='Filename of output image', default='1')
    parser.add_argument('--x-y', '-x', help='x y', default='0.85, 0.5')
    parser.add_argument('--viz', '-v', action='store_true',
                        help='Visualize the images as they are processed')
    parser.add_argument('--no-save', '-n', action='store_true', help='Do not save the output masks')
    parser.add_argument('--mask-threshold', '-t', type=float, default=0.5,
                        help='Minimum probability value to consider a mask pixel white')
    parser.add_argument('--scale', '-s', type=float, default=0.3,
                        help='Scale factor for the input images')
    parser.add_argument('--bilinear', action='store_true', default=False, help='Use bilinear upsampling')

    return parser.parse_args()




def mask_to_image(mask: np.ndarray):
    if mask.ndim == 2:
        return Image.fromarray((mask * 255).astype(np.uint8))
    elif mask.ndim == 3:
        return Image.fromarray((np.argmax(mask, axis=0) * 255 / mask.shape[0]).astype(np.uint8))


def add_draw(img, x_y):
    arr = x_y.split(',')
    w = img.size[0]
    h = img.size[1]
    if len(arr) % 2 == 0:
        arr = [float(x.strip()) for x in arr]
        arr2 = [(int(w*arr[i]), int(h*arr[i+1])) for i in range(0, len(arr), 2)]
        draw = ImageDraw.Draw(img)
        r = 20
        for x, y in arr2:
            a1 = x - r
            a2 = x
            b1 = y - r
            b2 = y
            draw.ellipse((a1, b1, a2, b2), fill='red', outline='red')
            a1 = x
            a2 = x + r
            b1 = y
            b2 = y + r
            draw.ellipse((a1, b1, a2, b2), fill='green', outline='red')
            a1 = x - r
            a2 = x
            b1 = y
            b2 = y + r
            draw.ellipse((a1, b1, a2, b2), fill='blue', outline='red')
            a1 = x
            a2 = x + r
            b1 = y - r
            b2 = y
            draw.ellipse((a1, b1, a2, b2), fill='yellow', outline='red')
    return img


def run_net(inp, id_file, x_y):
    net = UNet(n_channels=3, n_classes=2, bilinear=False)

    device = torch.device('cpu')
    # device = torch.device('cuda:1' if torch.cuda.is_available() else 'cpu')

    net.to(device=device)
    net.load_state_dict(torch.load('checkpoints/checkpoint_epoch200.pth', map_location=device))

    out_name = 'out/' + id_file + '.jpg'
    out_txt = 'out/' + id_file + '.txt'

    frame = cv2.imread(inp)
    img_raw = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(img_raw)
    img = add_draw(img, x_y)
    # img_raw = add_draw(img_raw, x_y)

    mask = predict_img(net=net,
                       full_img=img,
                       scale_factor=0.3,
                       out_threshold=0.5,
                       device=device)
    contours, hierarchy = cv2.findContours(mask[1].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    ndx = np.where(mask[1] == 1)

    arr = x_y.split(',')
    w = img.size[0]
    h = img.size[1]
    if len(arr) % 2 == 0:
        arr = [float(x.strip()) for x in arr]
        arr2 = [(int(w*arr[i]), int(h*arr[i+1])) for i in range(0, len(arr), 2)]
        for x, y in arr2:
            cv2.circle(img_raw, (x, y), 10, (255,0,0), 3, 1)



    img_raw[ndx[0], ndx[1],:] = (0.3*img_raw[ndx[0], ndx[1],:] + 0.7*np.array([96, 96, 196])).astype(np.uint8)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 100:
            cv2.drawContours(img_raw, [cnt], 0, (0, 255, 0), 3)

    img_raw = cv2.cvtColor(img_raw, cv2.COLOR_RGB2BGR)
    cv2.imwrite(out_name, img_raw)
    with open(out_txt, 'w') as f:
        for cnt in contours:
            cnt = cnt.astype(np.float)
            cnt[:, 0, 0] = cnt[:, 0, 0] / img_raw.shape[1]
            cnt[:, 0, 1] = cnt[:, 0, 1] / img_raw.shape[0]
            a = np.array2string(cnt.flatten(), separator=';').replace('\n', '')
            f.write(a+'\n')

    return contours


if __name__ == '__main__':
    # ts = time.time()
    args = get_args()
    in_files = args.input
    out_files = args.output
    x_y = args.x_y
    run_net(in_files, out_files, x_y)
    # print(time.time() - ts)