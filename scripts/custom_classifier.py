import argparse
import collections
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.neural_network import MLPClassifier
from sklearn.externals import joblib
from sklearn.model_selection import cross_val_score
from sklearn.metrics import precision_recall_fscore_support
from tripletools import get_best_features
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


plt.style.use('ggplot')

experiments = [
    {
        'name': 'Logistic Regression',
        'model': LogisticRegression(),
        'params': [
            {
                'solver': ['liblinear'],
                'penalty': ['l2'],
                'random_state': [77]
            },
        ]
    },
    {
        'name': 'SVM',
        'model': SVC(),
        'params': [
            {
                'kernel': ['poly'],
                'degree': [5],
                'random_state': [77]
            },
        ]
    },
    {
        'name': 'MLP',
        'model': MLPClassifier(max_iter=1000),
        'params': [
            {
                'hidden_layer_sizes': [(20, 10)],
                'random_state': [77]
            }
        ]
    },
    {
        'name': 'Random Forest',
        'model': RandomForestClassifier(),
        'params': [
            {
                'max_depth': [8],
                'n_estimators': [20],
                'min_samples_split': [5],
                'criterion': ['gini'],
                'max_features': ['auto'],
                'class_weight': ['balanced'],
                'random_state': [77]
            }
        ]
    },
]


def cross_validate_precision_recall_fbeta(model, X, y, cv=None):
    precision = cross_val_score(model, X, y, cv=cv, scoring='precision').mean()
    recall = cross_val_score(model, X, y, cv=cv, scoring='recall').mean()
    fbeta = cross_val_score(model, X, y, cv=cv, scoring='f1').mean()
    return precision, recall, fbeta


def plot_model_performance_comparison(experiments):
    fig, ax = plt.subplots()

    # Example data
    x_data = []
    y_dict = {
        'precision': {'color': '#f9f1c5', 'data': []},
        'recall': {'color': 'lightblue', 'data': []},
        'f1': {'color': 'green', 'data': []},
    }
    for exp in experiments:
        x_data.append(exp['name'])
        y_dict['precision']['data'].append(exp['best_score']['precision'])
        y_dict['recall']['data'].append(exp['best_score']['recall'])
        y_dict['f1']['data'].append(exp['best_score']['f1'])

    x = np.arange(len(x_data))
    width = 0.20
    i = 1
    legend_handles = []
    for label, y in y_dict.items():
        ax.bar(x + width * i, y['data'], width, color=y['color'])
        legend_handles.append(mpatches.Patch(color=y['color'], label=label))
        i += 1
    ax.set_xticks(x + width * 2)
    ax.set_xticklabels(x_data)
    ax.set_yticks(np.arange(0.0, 1.1, 0.1))
    ax.set_title('Triple Selector Models Performance')

    lgd = plt.legend(handles=legend_handles)
    plt.show()


def cross_val_hybrid_classifier(classifiers, X, y, cv=None):
    cv = 3 if not cv else cv
    scores = {'precision': [], 'recall': [], 'f1': []}
    for i in range(cv):
        test_size = 1.0 / cv
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size)
        classifiers[0].fit(X_train, y_train)
        classifiers[1].fit(X_train, y_train)
        y_predict = np.clip(classifiers[0].predict(X_test) + classifiers[1].predict(X_test), 0, 1)
        p, r, fb, su = precision_recall_fscore_support(y_test, y_predict, average='binary')
        scores['precision'].append(p)
        scores['recall'].append(r)
        scores['f1'].append(fb)
    precision = np.mean(scores['precision'])
    recall = np.mean(scores['recall'])
    fbeta = np.mean(scores['f1'])
    return precision, recall, fbeta


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train triples classifier')
    parser.add_argument('dataset_path', help='Dataset path')
    parser.add_argument('-o', '--output_path', help='Output model path', default='triples-classifier-model.pkl')
    parser.add_argument('-s', '--scaler_output_path', help='Output scaler path', default='triples-classifier-scaler.pkl')
    parser.add_argument('-b', '--best', help='search parameters that gives best model', action='store_true')
    args = parser.parse_args()

    # load dataset
    dataset = np.genfromtxt(args.dataset_path, delimiter=',', dtype='float32')
    total_features = dataset.shape[1] - 1

    # feature selection
    selected_features = get_best_features()
    print('Total features: {}'.format(total_features))
    print('Selected features: {} ({})'.format(selected_features, len(selected_features)))

    X = dataset[:, selected_features]
    y = dataset[:, -1]
    scaler = StandardScaler().fit(X)
    X = scaler.transform(X)
    joblib.dump(scaler, args.scaler_output_path)

    # collect dataset statistics
    counter = collections.Counter(y)
    print(counter)
    pos = counter[1] * 1.0 / (counter[0] + counter[1])
    neg = 1.0 - pos

    # exhaustive best parameters search
    cv = None
    print('')
    if args.best:
        best_score = 0.0
        best_model = None
        count = 0
        for experiment in experiments:
            search = GridSearchCV(
                estimator=experiment['model'],
                param_grid=experiment['params'],
                scoring='f1',
                cv=cv
            )
            search.fit(X, y)
            precision, recall, fbeta = cross_validate_precision_recall_fbeta(search.best_estimator_, X, y)
            print(search.best_estimator_)
            print('Precision: {}\nRecall: {}\nF1: {}\n'.format(
                precision,
                recall,
                fbeta
            ))
            experiment['best_model'] = search.best_estimator_
            experiment['best_score'] = {'precision': precision, 'recall': recall, 'f1': fbeta}
            # replace current best model if the score is higher
            if search.best_score_ > best_score:
                best_score = search.best_score_
                best_model = search.best_estimator_
            count += 1

        # combine SVM and Random Forest
        svm = experiments[0]['best_model']
        rf = experiments[1]['best_model']
        precision, recall, fbeta = cross_val_hybrid_classifier((svm, rf), X, y, cv)
        experiments.append({
            'name': 'SVM + RF',
            'best_score': {
                'precision': precision,
                'recall': recall,
                'f1': fbeta
            }
        })

        # print('--------------- Result ----------------')
        # print('Best models: {} (F1 = {})'.format(best_score, type(best_model).__name__))
        model = best_model

        # show plot
        plot_model_performance_comparison(experiments)

    else:
        svm = SVC(kernel='poly', degree=5, random_state=77)
        rf = RandomForestClassifier(max_depth=8, class_weight='balanced', n_estimators=20, min_samples_leaf=1, random_state=77)

        # cross validate best model to compare score
        cv = 3
        scores = {'precision': [], 'recall': [], 'f1': []}
        for i in range(cv):
            test_size = 1.0 / cv
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size)
            svm.fit(X_train, y_train)
            rf.fit(X_train, y_train)
            y_predict = np.clip(svm.predict(X_test) + rf.predict(X_test), 0, 1)
            p, r, fb, su = precision_recall_fscore_support(y_test, y_predict, average='binary')
            scores['precision'].append(p)
            scores['recall'].append(r)
            scores['f1'].append(fb)

        model = rf
        precision = np.mean(scores['precision'])
        recall = np.mean(scores['recall'])
        fbeta_array = np.array(scores['f1'])
        fbeta = fbeta_array.mean()
        fbeta_min = fbeta_array.min()
        fbeta_max = fbeta_array.max()
        fbeta_std = fbeta_array.std()

        print('Cross Validation K: {}'.format(cv))
        print('Precision avg: {}'.format(precision))
        print('Recall avg: {}'.format(recall))
        print('F1 avg: {}'.format(fbeta))
        print('F1 min: {}'.format(fbeta_min))
        print('F1 max: {}'.format(fbeta_max))
        print('F1 std: {}'.format(fbeta_std))

    # save model to file
    joblib.dump(model, args.output_path)
    print('Model saved to {}'.format(args.output_path))
    print('Scaler saved to {}'.format(args.scaler_output_path))
