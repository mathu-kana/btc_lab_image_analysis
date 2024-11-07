import random
import numpy as np
import os
from pathlib import Path
import shutil
import torch
from torchvision import datasets, transforms
from torchvision.transforms import v2
import torchvision.models as torchmodels
from torch.utils.data import DataLoader, Subset, random_split
from PIL import Image, UnidentifiedImageError
from tqdm import tqdm
from datetime import datetime
from collections import Counter
from cv2 import imread, imwrite


class FeatureDataset(datasets.DatasetFolder):
    def __init__(self, datapath: str, transform=None):
        """
        Arguments:
            datapath (string): Directory in which the class folders are located.
            transform (callable, optional): Optional transform to be applied
                on a sample.
        """
        super().__init__(
            root=datapath,
            loader=lambda path: torch.from_numpy(np.load(str(path))["arr_0"]),
            extensions=(".npz",),
            transform=transform,
        )


class TumorImageDataset(datasets.ImageFolder):
    def __init__(self, datapath: str, cases=[], transform=None):
        """
        Arguments:
            datapath (string): Directory in which the class folders are located.
            transform (callable, optional): Optional transform to be applied
                on a sample.
        """
        super().__init__(
            root=datapath,
            transform=transform,
            is_valid_file=lambda x: get_case(os.path.basename(x)) in cases,
        )

def load_training_image_data(batch_size, tumor_type, transforms=None, normalized=False):
    image_directory = f"./images/{tumor_type}/images"
    if normalized:
        image_directory = f"./images/{tumor_type}/normalized_images"
    print(f"\nLoading images from: {image_directory}")
    transforms = v2.Compose(
        [v2.RandomAffine(degrees=15, translate=(0.15, 0.15)), transforms]
    )
    print(image_directory)
    # get full data set
    full_train_dataset = datasets.ImageFolder(image_directory, transform=transforms)
    random_sampler = 
    # Split the datasets into training, validation, and testing sets
    # train_dataset, valid_dataset, test_dataset, _ = random_split(
    #     full_train_dataset,
    #     [
    #         int(train_size * 0.8),
    #         int(train_size * 0.1),
    #         int(train_size * 0.1),
    #         train_size - int(train_size * 0.8) - 2 * int(train_size * 0.1),
    #     ],
    # )
    train_dataset, valid_dataset, test_dataset = random_split(full_train_dataset,[10000,10000,10000])

    processing_transforms = transforms.Compose(
        [
            transforms.Resize((224, 224)),  # ResNet expects 224x224 images
            transforms.ToTensor(),  # Converts the image to a PyTorch tensor, which also scales the pixel values to the range [0, 1]
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
            ),  # Normalizes the image tensor using the mean and standard deviation values that were used when training the ResNet model (usually on ImageNet)
        ]
    )

    train_classes = dict(
        sorted(
            Counter(
                [full_train_dataset.targets[i] for i in train_dataset.indices]
            ).items()
        )
    )  # counter return a dictionnary of the counts, sort and wrap with dict to get dict sorted by key
    valid_classes = dict(
        sorted(
            Counter(
                [full_train_dataset.targets[i] for i in valid_dataset.indices]
            ).items()
        )
    )
    test_classes = dict(
        sorted(
            Counter(
                [full_train_dataset.targets[i] for i in test_dataset.indices]
            ).items()
        )
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=get_allowed_forks(),
    )
    valid_loader = DataLoader(
        valid_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=get_allowed_forks(),
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=get_allowed_forks(),
    )

    print(
        f"Training set size: {len(train_dataset)}, Class Proportions: {({full_train_dataset.classes[k]:v for k,v in train_classes.items()})}"
    )
    print(
        f"Validation set size: {len(valid_dataset)}, Class Proportions: {({full_train_dataset.classes[k]:v for k,v in valid_classes.items()})}"
    )
    print(
        f"Test set size: {len(test_dataset)}, Class Proportions: {({full_train_dataset.classes[k]:v for k,v in test_classes.items()})}"
    )

    return (train_loader, valid_loader, test_loader), (
        train_classes,
        valid_classes,
        test_classes,
    )


def load_training_image_data_by_case(
    batch_size, tumor_type, transforms=None, normalized=False
):
    image_directory = f"./images/{tumor_type}/images"
    if normalized:
        image_directory = f"./images/{tumor_type}/normalized_images"
    print(f"\nLoading images from: {image_directory}")

    transforms = v2.Compose(
        [v2.RandomAffine(degrees=15, translate=(0.15, 0.15)), transforms]
    )
    # get full data set
    # full_train_dataset = datasets.ImageFolder(image_directory,transform=transforms)
    total_size = get_size_of_dataset(
        image_directory, "jpg"
    )  # compute total size of dataset
    train_ratio, valid_ratio, test_ratio = 0.7, 0.2, 0.1
    # Split the datasets into training, validation, and testing sets
    cases = {k: len(v) for k, v in find_cases(image_directory).items()}
    label_sets = []
    for label in next(os.walk(image_directory))[1]:
        label_directory = os.path.join(image_directory, label)
        label_sets.append(set(find_cases(label_directory).keys()))
    intersection = set.intersection(*label_sets)
    reverse_sort_intersection = sorted(intersection, key=lambda x: cases[x])
    """
    We want to collect the intersection of cases for all labels (e.g. tumor, normal) 
    as we want both the test and train data to contain cases from this intersection
    the remaining data (most of this is cases that are only tumor) should be training
    we want to sort and reverse the intersection so that the first half is added to training
    """
    train_subset, test_subset = get_case_subsets(
        cases, reverse_sort_intersection, total_size * (1 - test_ratio)
    )  # gives us the subsets that contain equal amounts from intersection, and then fills training data until it reaches ratio
    # cases = {k:len(v) for k,v in find_cases(image_directory).items()}
    # print([cases[case] for case in train_subset if case in intersection])
    # print([cases[case] for case in test_subset if case in intersection])
    training_valid_dataset = TumorImageDataset(
        datapath=image_directory, cases=train_subset, transform=transforms
    )
    test_dataset = TumorImageDataset(
        datapath=image_directory, cases=test_subset, transform=transforms
    )

    train_valid_size = len(training_valid_dataset)
    train_size, valid_size = (
        int(train_valid_size * (train_ratio / (train_ratio + valid_ratio))),
        int(train_valid_size * (valid_ratio / (train_ratio + valid_ratio))),
    )

    train_dataset, valid_dataset, _ = random_split(
        training_valid_dataset,
        [train_size, valid_size, train_valid_size - train_size - valid_size],
    )

    train_classes = dict(
        sorted(
            Counter(
                [training_valid_dataset.targets[i] for i in train_dataset.indices]
            ).items()
        )
    )  # counter return a dictionnary of the counts, sort and wrap with dict to get dict sorted by key
    valid_classes = dict(
        sorted(
            Counter(
                [training_valid_dataset.targets[i] for i in valid_dataset.indices]
            ).items()
        )
    )
    test_classes = dict(sorted(Counter(test_dataset.targets).items()))

    # print(train_classes,valid_classes,test_classes)

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=get_allowed_forks(),
    )
    valid_loader = DataLoader(
        valid_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=get_allowed_forks(),
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=get_allowed_forks(),
    )
    print(training_valid_dataset.classes)
    print(
        f"Training set size: {len(train_dataset)}, Class Proportions: {({training_valid_dataset.classes[k]:v for k,v in train_classes.items()})}"
    )
    print(
        f"Validation set size: {len(valid_dataset)}, Class Proportions: {({training_valid_dataset.classes[k]:v for k,v in valid_classes.items()})}"
    )
    print(
        f"Test set size: {len(test_dataset)}, Class Proportions: {({training_valid_dataset.classes[k]:v for k,v in test_classes.items()})}"
    )

    return (train_loader, valid_loader, test_loader), (
        train_classes,
        valid_classes,
        test_classes,
    )

def get_size_of_dataset(directory, extension):
    return len([path for path in Path(directory).rglob(f"*.{extension}")])


def get_annotation_classes(tumor_type):
    image_directory = f"./images/{tumor_type}/images"
    return [
        name
        for name in os.listdir(image_directory)
        if name not in [".DS_Store", "__MACOSX"]
    ]

def check_for_unopenable_files(tumor_type, norm = False):
    if norm:
        image_directory = f"./images/{tumor_type}/normalized_images"
    else:
        image_directory = f"./images/{tumor_type}/images"
    with open(file=f"./results/{tumor_type}_corrupted_files.txt", mode="w") as f:
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"Checked on {time}\n")
        images_paths = [path for path in Path(image_directory).rglob("*.jpg")]
        for image_path in tqdm(images_paths):
            try:
                Image.open(image_path)
                cv2image = imread(str(image_path))
                if cv2image is None:
                    raise UnidentifiedImageError
            except UnidentifiedImageError:
                f.write(str(image_path))

def split_all_images(tumor_type,norm = False):
    '''
    Splits all 512 x 512 image into 4 256 x 256 tiles, saves them and deletes original
    '''
    if norm:
        image_directory = f"./images/{tumor_type}/normalized_images"
    else:
        image_directory = f"./images/{tumor_type}/images"
    for annotation in os.listdir(image_directory):
        if annotation in [".DS_Store", "__MACOSX"]:
            continue
        for image_path in tqdm(os.listdir(os.path.join(image_directory,annotation))):
            if 'tile' in image_path:
                continue
            image_full_path = (os.path.join(image_directory,annotation,image_path))
            image = imread(image_full_path)
            if image.shape == (512,512,3):
                for idx,tile in enumerate([image[x:x+256,y:y+256] for x in range(0,512,256) for y in range (0,512,256)]):
                    # print(os.path.splitext(image_full_path)[0]+f"_tile_{idx+1}"+os.path.splitext(image_full_path)[1])
                    imwrite(os.path.splitext(image_full_path)[0]+f"_tile_{idx+1}"+os.path.splitext(image_full_path)[1],tile)
                os.remove(image_full_path)

def get_case_subsets(case_dict, intersection, max_size):
    train_subset = []
    test_subset = []
    total = 0  # used to track if we go past max size
    for i, inter_case in enumerate(intersection):
        if (
            total + case_dict[inter_case] >= max_size
        ):  # if we get to max value from intersection (unlikely) quit
            break
        if i > (
            len(intersection) // 2
        ):  # for the latter half (biggest values), add to train
            train_subset.append((inter_case, case_dict[inter_case]))
            total += case_dict.pop(inter_case)
        else:  # second half, add to test
            test_subset.append((inter_case, case_dict[inter_case]))
            case_dict.pop(inter_case)
    cases = iter(
        reversed(sorted(list(case_dict.items()), key=lambda x: x[1]))
    )  # turn remaining cases into interable
    while True:
        try:
            case = next(cases)
        except StopIteration:  # break immediately if no more options
            break
        value = case[1]
        if total + value >= max_size:
            test_subset = test_subset + [case] + list(cases)
            break
        train_subset.append(case)
        total += value
    return [case[0] for case in train_subset], [case[0] for case in test_subset]


def get_case(path: str) -> str:
    """
    extracts case from image filepath, assuming "case" is everything before the last _ for the filename
    """
    return os.path.basename(path).rsplit("_", 1)[0]


def find_cases(image_directory):
    paths = [path for path in Path(image_directory).rglob("*.jpg")]
    cases = list(set([get_case(str(path)) for path in paths]))
    case_dict = {
        case: sorted(
            [
                os.path.join(path.parent, path.name)
                for path in paths
                if case in path.name
            ]
        )
        for case in cases
    }
    return case_dict

def compute_mean_std_per_channel(full_data_loader):
    pass


def count_dict_tensor(count_dict: dict):
    """
    Converts a dictionnary of the count of each class (returned by load_training_feature_data) into a 1D tensor (required for weighted cross entropy loss)
    """
    return torch.tensor(
        [sum(count_dict.values()) / count_dict[k] for k in sorted(count_dict.keys())]
    )


def get_allowed_forks():
    if os.name == "nt":
        return 0
    return 8


if __name__ == "__main__":
    # load_data("vMRT",99,1000)
    # load_feature_data(100,"VMRT",99,100)

    tumor_type = "DDC_UC_1"
    image_directory = f"./images/{tumor_type}/images"
    seed = 99
    # print(*list(os.listdir('./images/DDC_UC_1/normalized_images/undiff')),sep='\n')
    # x = imread('./images/DDC_UC_1/normalized_images/undiff/AS19060903_275284.jpg_tile_3')
    for tumor_type in os.listdir('images'):
        image_directory = f"./images/{tumor_type}/normalized_images"
        if tumor_type in [".DS_Store", "__MACOSX"]:
            continue
        print(tumor_type)
        check_for_unopenable_files(tumor_type)


