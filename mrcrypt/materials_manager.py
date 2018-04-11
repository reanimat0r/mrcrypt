"""
mrcrypt.materials_manager
~~~~~~~~~~~~~~~~~~~~~~~~~

Legacy compatibility crypto materials manager class to enable reading
files created with legacy mrcrypt formatting.
"""
import base64
import logging

from aws_encryption_sdk.exceptions import AWSEncryptionSDKClientError
from aws_encryption_sdk.internal.defaults import ENCODED_SIGNER_KEY
from aws_encryption_sdk.materials_managers import DecryptionMaterials
from aws_encryption_sdk.materials_managers.default import DefaultCryptoMaterialsManager
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicNumbers

_LOGGER = logging.getLogger('mrcrypt')


class MrcryptLegacyCompatibilityCryptoMaterialsManager(DefaultCryptoMaterialsManager):
    """Cryptographic materials manager that provides decrypt compatibility with the
    uncompressed elliptic curve points generated by previous versions of mrcrypt.

    :param master_key_provider: Master key provider to use
    :type master_key_provider: aws_encryption_sdk.key_providers.base.MasterKeyProvider
    """

    def _load_uncompressed_verification_key_from_encryption_context(self, algorithm, encryption_context):
        # pylint: disable=no-self-use
        """Loads the verification key from an uncompressed elliptic curve point.

        :param algorithm: Algorithm for which to generate signing key
        :type algorithm: aws_encryption_sdk.identifiers.Algorithm
        :param dict encryption_context: Encryption context from request
        :returns: Raw verification key
        :rtype: bytes
        """
        # If we are at this point, DefaultCryptoMaterialsManager has already confirmed that:
        #  a) a key should be loaded,
        #  b) the key field is present in the encryption context, and
        #  c) the elliptic curve in the encryption context is not compressed
        # This means that we can safely skip the safety checks that we know have already been done.
        uncompressed_point = base64.b64decode(encryption_context[ENCODED_SIGNER_KEY])
        public_key = EllipticCurvePublicNumbers.from_encoded_point(
            curve=algorithm.signing_algorithm_info(),
            data=uncompressed_point
        ).public_key(default_backend())
        return public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def decrypt_materials(self, request):
        """Obtains a plaintext data key from one or more encrypted data keys
        using underlying master key provider.

        :param request: decrypt materials request
        :type request: aws_encryption_sdk.materials_managers.DecryptionMaterialsRequest
        :returns: decryption materials
        :rtype: aws_encryption_sdk.materials_managers.DecryptionMaterials
        """
        try:
            return super(MrcryptLegacyCompatibilityCryptoMaterialsManager, self).decrypt_materials(request)
        except (AWSEncryptionSDKClientError, KeyError):
            _LOGGER.debug(
                'Encountered error decrypting materials with DefaultCryptoMaterialsManager.'
                ' Attempting to decrypt using uncompressed elliptic curve point.'
            )
            # Once this issue is addressed, the caught exception classes should be narrowed appropriately:
            # https://github.com/awslabs/aws-encryption-sdk-python/issues/21

            _LOGGER.warning("This file is encrypted using an uncompressed key, which may lead to compatibility issues "
                            "with the AWS Encryption SDK.")

        data_key = self.master_key_provider.decrypt_data_key_from_list(  # subclasses confuse pylint: disable=no-member
            encrypted_data_keys=request.encrypted_data_keys,
            algorithm=request.algorithm,
            encryption_context=request.encryption_context
        )
        verification_key = self._load_uncompressed_verification_key_from_encryption_context(
            algorithm=request.algorithm,
            encryption_context=request.encryption_context
        )

        return DecryptionMaterials(
            data_key=data_key,
            verification_key=verification_key
        )