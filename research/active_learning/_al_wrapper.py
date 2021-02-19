"""
A wrapper to allow an automated Active Learning procedure for an
experimental environment.
"""

# Author: Joao Fonseca <jpmrfonseca@gmail.com>
# License: MIT

import numpy as np
from sklearn.base import clone
from sklearn.base import ClassifierMixin, BaseEstimator
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from imblearn.pipeline import Pipeline
from ..metrics import SCORERS
from ._selection_methods import SELECTION_CRITERIA
from ._init_methods import init_strategy


class ALWrapper(ClassifierMixin, BaseEstimator):
    def __init__(
        self,
        classifier=None,
        generator=None,
        init_clusterer=None,
        init_strategy='random',
        selection_strategy='entropy',
        max_iter=None,
        n_initial=100,
        increment=50,
        save_classifiers=False,
        save_test_scores=True,
        auto_load=True,
        test_size=.1,
        evaluation_metric='accuracy',
        random_state=None
    ):
        """
        A wrapper to allow an automated Active Learning procedure for an
        experimental environment.
        """
        self.classifier = classifier
        self.generator = generator
        self.init_clusterer = init_clusterer
        self.init_strategy = init_strategy
        self.selection_strategy = selection_strategy
        self.max_iter = max_iter
        self.n_initial = n_initial
        self.increment = increment

        # Used to find the optimal classifier
        self.auto_load = auto_load
        self.test_size = test_size
        self.save_classifiers = save_classifiers
        self.save_test_scores = save_test_scores
        self.evaluation_metric = evaluation_metric

        self.random_state = random_state

    def _check(self, X, y):

        if self.evaluation_metric is None:
            self.evaluation_metric_ = SCORERS['accuracy']
        elif type(self.evaluation_metric) == str:
            self.evaluation_metric_ = SCORERS[self.evaluation_metric]
        else:
            self.evaluation_metric_ = self.evaluation_metric

        if self.classifier is None:
            self._classifier = RandomForestClassifier(
                random_state=self.random_state
            )
        else:
            self._classifier = clone(self.classifier)

        if type(self.selection_strategy) == str:
            self.selection_strategy_ = SELECTION_CRITERIA[
                self.selection_strategy
            ]
        else:
            self.selection_strategy_ = self.selection_strategy

        self.max_iter_ = self.max_iter \
            if self.max_iter is not None \
            else np.inf

        if self.save_classifiers or self.save_test_scores:
            self.data_utilization_ = []

        if self.save_classifiers:
            self.classifiers_ = []

        if self.save_test_scores:
            self.test_scores_ = []

        if self.auto_load:
            self.classifier_ = None
            self._top_score = 0

        if self.auto_load or self.save_test_scores:
            X, X_test, y, y_test = train_test_split(
                X, y,
                test_size=self.test_size,
                random_state=self.random_state,
                stratify=y
            )
        else:
            X_test, y_test = (None, None)

        self.increment_ = self.increment
        return X, X_test, y, y_test

    def _get_performance_scores(self):
        data_utilization = [
            i[1] for i in self.data_utilization_
        ]
        test_scores = self.test_scores_
        return data_utilization, test_scores

    def _save_metadata(self, iter_n, classifier, X_test, y_test, selection):
        """Save metadata from a completed iteration."""

        # Get score for current iteration
        if self.save_test_scores or self.auto_load:
            score = self.evaluation_metric_(
                classifier,
                X_test,
                y_test
            )

        # Save classifier
        if self.save_classifiers:
            self.classifiers_.append(classifier)

        # Save test scores
        if self.save_test_scores:
            self.test_scores_.append(score)

            # TODO: This is useless. DUR can be calculated without this
            #       list. Just need to adapt the code accordingly.
            self.data_utilization_.append(
                (selection.sum(), selection.sum()/selection.shape[0])
            )

        # Replace top classifier
        if self.auto_load:
            if score > self._top_score:
                self._top_score = score
                self.classifier_ = classifier
                self.top_score_iter_ = iter_n

    def fit(self, X, y):

        # Original "unlabeled" dataset
        iter_n = 0
        X, X_test, y, y_test = self._check(X, y)
        selection = np.zeros(shape=(X.shape[0])).astype(bool)

        # Oracle - Get data according to passed initialization method
        self.init_clusterer_, ids = init_strategy(
            X=X,
            n_initial=self.n_initial,
            clusterer=self.init_clusterer,
            selection_method=self.init_strategy,
            random_state=self.random_state
        )

        selection[ids] = True

        while iter_n < self.max_iter_:

            # Generator + Chooser (in this case chooser==Predictor)
            generator = (
                None if self.generator is None else clone(self.generator)
            )
            chooser = clone(self._classifier)

            classifier = Pipeline([
                ('generator', generator),
                ('chooser', chooser)
            ])

            # Train classifier and get probabilities
            classifier.fit(X[selection], y[selection])

            # Save metadata from current iteration
            self._save_metadata(
                iter_n, classifier, X_test, y_test, selection
            )

            # Compute the class probabilities of unlabeled observations
            unlabeled_ids = np.argwhere(~selection).squeeze()
            probabs = classifier.predict_proba(X[~selection])

            # Some selection strategies can't deal with 0. values
            probabs = np.where(probabs == 0., 1e-10, probabs)

            # Get data according to passed selection criterion
            ids = self.selection_strategy_(
                probabilities=probabs,
                unlabeled_ids=unlabeled_ids,
                increment=self.increment_,
                random_state=self.random_state
            )

            # keep track of iter_n
            iter_n += 1

            # stop if all examples have been included
            if selection.all():
                break
            elif selection.sum()+self.increment_ > y.shape[0]:
                self.increment_ = y.shape[0] - selection.sum()

        return self

    def load_best_classifier(self, X, y):
        scores = []
        for classifier in self.classifiers_:
            scores.append(
                self.evaluation_metric_(classifier, X, y)
            )

        self.classifier_ = self.classifiers_[np.argmax(scores)]
        return self

    def predict(self, X):
        return self.classifier_.predict(X)
