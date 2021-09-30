
const urlParamsObj = {
    login: "?view=login",
    loginErrored: "?view=login&errored=true",
    loginProfileDoesNotExist: "?view=login&profile_does_not_exist=true",
    loginProfileIsNotPublic: "?view=login&profile_is_not_public=true",
};

const fieldSetsObj = {

    loginFieldSet: document.querySelector("#loginFieldset"),
    loginInputs: document.querySelectorAll("#loginFieldset input"),

    loginErrorFieldset: document.querySelector("#loginErrorFieldset"),
    loginErroredInputs: document.querySelectorAll("#loginErrorFieldset input"),

    loginProfileDoesNotExistFieldset: document.querySelector("#loginProfileDoesNotExistFieldset"),
    loginProfileDoesNotExistInputs: document.querySelectorAll("#loginProfileDoesNotExistFieldset input"),

    loginProfileIsNotPublicFieldset: document.querySelector("#loginProfileIsNotPublicFieldset"),
    loginProfileIsNotPublicInputs: document.querySelectorAll("#loginProfileIsNotPublicFieldset input"),

}

function handleEnablingInputs(inputs) {
    for (let i = 0; i < inputs.length; i++) {
        inputs[i].disabled = false;
    }
}

function handleParamsAndFormAction() {
    const url = window.location.search;
    const formElement = document.querySelector("#main-form");

    switch (url) {
        case urlParamsObj.login:
            fieldSetsObj.loginFieldSet.style.display = "block";
            handleEnablingInputs(fieldSetsObj.loginInputs);
            formElement.action = "/login_finished";
            break;
        case urlParamsObj.loginErrored:
            fieldSetsObj.loginErrorFieldset.style.display = "block";
            handleEnablingInputs(fieldSetsObj.loginErroredInputs);
            formElement.action = "/login_finished";
            break;
        case urlParamsObj.loginProfileDoesNotExist:
            fieldSetsObj.loginProfileDoesNotExistFieldset.style.display = "block";
            handleEnablingInputs(fieldSetsObj.loginProfileDoesNotExistInputs);
            formElement.action = "/login_finished";
            break;
        case urlParamsObj.loginProfileIsNotPublic:
            fieldSetsObj.loginProfileIsNotPublicFieldset.style.display = "block";
            handleEnablingInputs(fieldSetsObj.loginProfileIsNotPublicInputs);
            formElement.action = "/login_finished";
            break;
        default:
            fieldSetsObj.loginFieldSet.style.display = "block";
            handleEnablingInputs(fieldSetsObj.loginInputs);
            formElement.action = "/login_finished";
    }
}
window.addEventListener("load", handleParamsAndFormAction);
